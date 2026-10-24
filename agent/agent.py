"""LangChain proposal agent hosted by Vertex AI Agent Runtime."""

import json
import os


class QuoteAgent:
    def set_up(self):
        from opentelemetry import trace
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from openinference.instrumentation.langchain import LangChainInstrumentor

        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if project:
            provider = TracerProvider()
            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=project)))
            trace.set_tracer_provider(provider)
            LangChainInstrumentor().instrument()
        provider = os.environ.get("MODEL_PROVIDER", "vertexai")
        model_name = os.environ.get("MODEL_NAME", "gemini-3.5-flash")
        if provider == "vertexai":
            from langchain_google_vertexai import ChatVertexAI
            options = {"model_name": model_name, "location": os.environ.get("MODEL_REGION", "eu"),
                       "response_mime_type": "application/json", "temperature": 0}
            if project:
                options["project"] = project
            endpoint = os.environ.get("MODEL_API_ENDPOINT")
            if endpoint:
                options["api_endpoint"] = endpoint
            self.model = ChatVertexAI(**options)
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            self.model = ChatOpenAI(model=model_name, temperature=0)
        else:
            raise ValueError(f"unsupported model provider: {provider}")

    def query(self, input: str) -> dict:
        """Select published offerings from a request; output is untrusted until validated."""
        from opentelemetry import trace
        from opentelemetry.propagate import extract
        from langchain_core.messages import HumanMessage, SystemMessage
        payload = json.loads(input)
        allowed = payload["catalogue"]
        request = payload["request"]
        parent = extract(payload.get("traceContext", {}))
        with trace.get_tracer(__name__).start_as_current_span("agent.propose", context=parent):
            response = self.model.invoke([
                SystemMessage(content=(
                    "You configure telecom products. Select only Active product offering IDs in the supplied catalogue. "
                    "Match the requested allowances to the offering's composite product specification. "
                    "Return one JSON object with productOfferingIds (array of IDs), discountPercent (number, default 0), "
                    "exceptionRequested (boolean), and reason (short string). Do not invent prices or eligibility. "
                    "Do not add markdown or commentary."
                )),
                HumanMessage(content=json.dumps({"catalogue": allowed, "request": request}))
            ])
        content = response.content
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return json.loads(content)


root_agent = QuoteAgent()
