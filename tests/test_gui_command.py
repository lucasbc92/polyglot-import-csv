"""Assembling the CLI argv and the text shown in the console panel."""

from pathlib import Path

from polyglotimportcsv.gui.command import build_argv, is_program_token, to_display
from polyglotimportcsv.gui.state import RunOptions

CFG = Path("/proj/import_config.json")


def test_the_default_state_spells_every_option_out():
    """Q1: a control at its default value must still appear in the command.

    The first version emitted only what differed from the CLI defaults, so
    clicking "optimized", "stream" or "Criar esquema" produced no visible
    change and the control looked dead. Verbosity is the point here: the shown
    command is a teaching aid, not the shortest line a person could type.
    """
    assert build_argv(RunOptions(config_path=CFG)) == [
        "--config", str(CFG),
        "--strategy", "optimized",
        "--execution", "stream",
        "--create-schema",
        "--log-level", "INFO",
    ]


def test_sgbd_config_is_emitted_when_set():
    sgbd = Path("/proj/sgbd.json")
    argv = build_argv(RunOptions(config_path=CFG, sgbd_config_path=sgbd))
    assert argv[2:4] == ["--sgbd-config", str(sgbd)]


def test_only_is_comma_joined():
    argv = build_argv(RunOptions(config_path=CFG, only=("postgres", "redis")))
    assert "--only" in argv
    assert argv[argv.index("--only") + 1] == "postgres,redis"


def test_default_strategy_and_execution_are_emitted_too():
    argv = build_argv(RunOptions(config_path=CFG, strategy="optimized", execution="stream"))
    assert argv[argv.index("--strategy") + 1] == "optimized"
    assert argv[argv.index("--execution") + 1] == "stream"


def test_non_default_strategy_and_execution_are_emitted():
    argv = build_argv(RunOptions(config_path=CFG, strategy="naive", execution="materialize"))
    assert argv[argv.index("--strategy") + 1] == "naive"
    assert argv[argv.index("--execution") + 1] == "materialize"


def test_boolean_flags():
    argv = build_argv(RunOptions(config_path=CFG, dry_run=True, create_schema=False, benchmark=True))
    assert "--dry-run" in argv
    assert "--no-create-schema" in argv
    assert "--benchmark" in argv


def test_create_schema_emits_one_of_its_two_forms():
    on = build_argv(RunOptions(config_path=CFG, create_schema=True))
    assert "--create-schema" in on
    assert "--no-create-schema" not in on


def test_log_level_is_always_emitted():
    default = build_argv(RunOptions(config_path=CFG, log_level="INFO"))
    assert default[default.index("--log-level") + 1] == "INFO"
    argv = build_argv(RunOptions(config_path=CFG, log_level="DEBUG"))
    assert argv[argv.index("--log-level") + 1] == "DEBUG"


def test_show_data_tri_state():
    assert "--show-data" not in build_argv(RunOptions(config_path=CFG, show_data=None))
    assert "--no-data" not in build_argv(RunOptions(config_path=CFG, show_data=None))
    assert "--show-data" in build_argv(RunOptions(config_path=CFG, show_data=True))
    assert "--no-data" in build_argv(RunOptions(config_path=CFG, show_data=False))


def test_sources_are_repeated_pairs():
    argv = build_argv(
        RunOptions(
            config_path=CFG,
            sources=(("stock", Path("/d/stock.csv")), ("purchase", Path("/d/purchase.csv"))),
        )
    )
    assert argv.count("--source") == 2
    assert "stock=" + str(Path("/d/stock.csv")) in argv


def test_argv_follows_the_order_of_the_spec_table():
    """§4.2 fixes the order of the emitted flags, not merely that it repeats.

    The previous version of this test compared build_argv(o) to build_argv(o),
    which is true of any deterministic function and would have passed with the
    flags emitted in any order at all.
    """
    sgbd = Path("/proj/sgbd.json")
    source = Path("/proj/dados.csv")
    options = RunOptions(
        config_path=CFG,
        sgbd_config_path=sgbd,
        only=("postgres", "redis"),
        strategy="naive",
        execution="materialize",
        dry_run=True,
        create_schema=False,
        benchmark=True,
        log_level="DEBUG",
        show_data=True,
        sources=(("clientes", source),),
    )
    assert build_argv(options) == [
        "--config", str(CFG),
        "--sgbd-config", str(sgbd),
        "--only", "postgres,redis",
        "--strategy", "naive",
        "--execution", "materialize",
        "--dry-run",
        "--no-create-schema",
        "--benchmark",
        "--log-level", "DEBUG",
        "--show-data",
        "--source", "clientes={0}".format(source),
    ]


def test_every_option_changes_the_command_when_toggled():
    """Q1: no control may be a no-op, in either direction.

    Written as a sweep rather than one case per flag because the bug was not in
    any single flag but in the rule they all shared: skip whatever matches the
    CLI default.
    """
    base = RunOptions(config_path=CFG)
    flipped = (
        RunOptions(config_path=CFG, strategy="naive"),
        RunOptions(config_path=CFG, execution="materialize"),
        RunOptions(config_path=CFG, dry_run=True),
        RunOptions(config_path=CFG, create_schema=False),
        RunOptions(config_path=CFG, benchmark=True),
        RunOptions(config_path=CFG, log_level="DEBUG"),
        RunOptions(config_path=CFG, show_data=True),
        RunOptions(config_path=CFG, show_data=False),
        RunOptions(config_path=CFG, only=("redis",)),
    )
    for options in flipped:
        assert build_argv(options) != build_argv(base)


def test_argv_order_is_stable_when_options_are_at_their_defaults():
    """The spelled-out defaults keep the order of the §4.2 table."""
    argv = build_argv(RunOptions(config_path=CFG, only=("postgres",)))
    assert argv == [
        "--config", str(CFG),
        "--only", "postgres",
        "--strategy", "optimized",
        "--execution", "stream",
        "--create-schema",
        "--log-level", "INFO",
    ]


def test_display_prefixes_the_program_name():
    text = to_display(build_argv(RunOptions(config_path=CFG)), windows=False)
    assert text.startswith("polyglotimportcsv --config ")


def test_display_quotes_paths_with_spaces_on_windows():
    text = to_display(["--config", r"C:\meus arquivos\cfg.json"], windows=True)
    assert text == 'polyglotimportcsv --config "C:\\meus arquivos\\cfg.json"'


def test_display_quotes_paths_with_spaces_on_posix():
    text = to_display(["--config", "/meus arquivos/cfg.json"], windows=False)
    assert text == "polyglotimportcsv --config '/meus arquivos/cfg.json'"


def test_display_leaves_plain_tokens_unquoted():
    assert to_display(["--dry-run"], windows=True) == "polyglotimportcsv --dry-run"


# -- I5: telling the program name apart from an argument -------------------


def test_bare_program_name_is_recognised():
    assert is_program_token("polyglotimportcsv")


def test_program_name_with_exe_suffix_is_recognised():
    assert is_program_token("polyglotimportcsv.exe")


def test_program_name_with_a_path_prefix_is_recognised():
    assert is_program_token(r"C:\venv\Scripts\polyglotimportcsv.exe")
    assert is_program_token("/usr/local/bin/polyglotimportcsv")
    assert is_program_token(r'"C:\meu venv\Scripts\polyglotimportcsv.exe"')


def test_an_option_is_not_the_program_name():
    assert not is_program_token("--dry-run")
    assert not is_program_token("--config")


def test_another_program_is_not_the_program_name():
    assert not is_program_token("python")
    assert not is_program_token("polyglotimportcsv-gui")
