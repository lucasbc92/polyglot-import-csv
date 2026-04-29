import click

from polyglotimportcsv.database_parsers import (
    cassandra,
    mongodb,
    neo4j,
    postgres,
    redis,
)


class EnumDatabaseParsers(click.ParamType):
    name = 'enum'

    enum_database_parsers = {
        'postgres': postgres,
        'mongodb': mongodb,
        'cassandra': cassandra,
        'redis': redis,
        'neo4j': neo4j,
    }

    def convert(self, value, param, ctx):
        if value not in self.enum_database_parsers:
            self.fail(
                f'Invalid value "{value}". Choose from: '
                f'{", ".join(self.enum_database_parsers.keys())}',
                param,
                ctx,
            )
        return self.enum_database_parsers[value]
