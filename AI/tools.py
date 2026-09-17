import json

from agents import function_tool



@function_tool
def call_graphql(query: str) -> str:
    return True
