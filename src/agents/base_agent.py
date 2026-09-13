from ..tools.registry import specs_for_agent


class BaseAgent:
    agent_name = "base_agent"

    def __init__(self, executor, registry, llm_client=None):
        self.executor = executor
        self.registry = registry
        self.llm_client = llm_client

    @property
    def tool_specs(self):
        return specs_for_agent(self.registry, self.agent_name)

    def call_tool(self, session_id, name, **arguments):
        return self.executor.execute(session_id, self.agent_name, name, arguments)
