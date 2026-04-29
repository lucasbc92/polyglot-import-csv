import json
import logging

import click
import pandas as pd

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.enum_database_parsers import EnumDatabaseParsers

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class OrderedParamsCommand(click.Command):
    def parse_args(self, ctx, args):
        self._options = []
        parser = self.make_parser(ctx)
        opts, _, param_order = parser.parse_args(args=list(args))
        for param in param_order:
            if not isinstance(opts[param.name], list):
                self._options.append((param, opts[param.name]))
            else:
                self._options.append((param, opts[param.name].pop(0)))

        return super().parse_args(ctx, args)

    @property
    def options(self):
        return self._options


parsers = EnumDatabaseParsers.enum_database_parsers


@click.command(cls=OrderedParamsCommand)
@click.pass_context
@click.argument('csvfile', type=click.File('r'))
@click.option('--dbconfig', type=click.File('r'), required=False, default='',
              help='JSON database configuration file. If omitted, '
                   'there will be needed to pass database credentials through command line.')
@click.option('--database', '-d', type=click.Choice(parsers.keys()),
              multiple=True)
@click.option('--entity', type=str, multiple=True)
@click.option('--rel', type=str, multiple=True, required=False, default=[])
def main(ctx, csvfile, dbconfig, database, entity, rel):
    """CSVFILE: CSV file to be imported"""
    df = pd.read_csv(csvfile)
    print(df)
    if dbconfig:
        print("Has dbconfig file")
        config = json.load(dbconfig)
        print(config)

    current_parser = None
    current_entities = []
    current_relationships = None

    for option, value in ctx.command.options:
        if option.name == 'database':
            if current_parser:
                result = current_parser(current_entities) if current_relationships is None \
                    else current_parser(current_entities, current_relationships)
                print(result)
            current_parser = parsers[value]
            current_entities = []
            current_relationships = [] if value == 'postgres' or value == 'neo4j' else None
        elif option.name == 'entity':
            current_entities.append(value)
        elif option.name == 'rel':
            try:
                current_relationships.append(value)
            except Exception:
                raise BusinessException(
                    current_parser.__name__ + " does not support relationships."
                )
    if current_parser:
        result = current_parser(current_entities) if current_relationships is None \
            else current_parser(current_entities, current_relationships)
        print(result)
