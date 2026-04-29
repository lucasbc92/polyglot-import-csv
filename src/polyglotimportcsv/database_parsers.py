def postgres(entities, relationships):
    print('postgres')
    return [entities, relationships]


def mongodb(entities):
    print('mongodb')
    return entities


def cassandra(entities):
    print('cassandra')
    return entities


def redis(entities):
    print('redis')
    return entities


def neo4j(entities, relationships):
    print('neo4j')
    return [entities, relationships]
