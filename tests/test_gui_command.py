"""Assembling the CLI argv and the text shown in the console panel."""

from pathlib import Path

from polyglotimportcsv.gui.command import build_argv, to_display
from polyglotimportcsv.gui.state import RunOptions

CFG = Path("/proj/import_config.json")


def test_only_config_in_the_default_state():
    assert build_argv(RunOptions(config_path=CFG)) == ["--config", str(CFG)]


def test_sgbd_config_is_emitted_when_set():
    sgbd = Path("/proj/sgbd.json")
    argv = build_argv(RunOptions(config_path=CFG, sgbd_config_path=sgbd))
    assert argv[2:] == ["--sgbd-config", str(sgbd)]


def test_only_is_comma_joined():
    argv = build_argv(RunOptions(config_path=CFG, only=("postgres", "redis")))
    assert "--only" in argv
    assert argv[argv.index("--only") + 1] == "postgres,redis"


def test_default_strategy_and_execution_are_omitted():
    argv = build_argv(RunOptions(config_path=CFG, strategy="optimized", execution="stream"))
    assert "--strategy" not in argv
    assert "--execution" not in argv


def test_non_default_strategy_and_execution_are_emitted():
    argv = build_argv(RunOptions(config_path=CFG, strategy="naive", execution="materialize"))
    assert argv[argv.index("--strategy") + 1] == "naive"
    assert argv[argv.index("--execution") + 1] == "materialize"


def test_boolean_flags():
    argv = build_argv(RunOptions(config_path=CFG, dry_run=True, create_schema=False, benchmark=True))
    assert "--dry-run" in argv
    assert "--no-create-schema" in argv
    assert "--benchmark" in argv


def test_create_schema_true_emits_nothing():
    assert "--create-schema" not in build_argv(RunOptions(config_path=CFG, create_schema=True))
    assert "--no-create-schema" not in build_argv(RunOptions(config_path=CFG, create_schema=True))


def test_log_level_only_when_not_info():
    assert "--log-level" not in build_argv(RunOptions(config_path=CFG, log_level="INFO"))
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
