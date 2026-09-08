import strawberry

from api.schema.query import Query

schema = strawberry.Schema(query=Query)
