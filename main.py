import os
import time
import json
from typing import Dict, Any, List, Optional
import logging

from langchain_core.agents import AgentFinish
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnablePassthrough
from langchain.agents import AgentExecutor, create_react_agent
from langchain.chains import LLMChain
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.memory import ConversationBufferWindowMemory
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from langchain_openai import OpenAIEmbeddings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration and Environment Loading ---
# In a real app, this would be more robust with pydantic settings
class Config:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "infra_pilot_knowledge")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
    MEMORY_WINDOW_SIZE = int(os.getenv("MEMORY_WINDOW_SIZE", "5"))

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable not set.")

config = Config()

# --- LLM and Embeddings Setup ---
llm = ChatOpenAI(model=config.LLM_MODEL, temperature=config.TEMPERATURE, api_key=config.OPENAI_API_KEY)
embeddings = OpenAIEmbeddings(api_key=config.OPENAI_API_KEY)

# --- Persistent Knowledge Base (Qdrant) ---
def get_knowledge_base():
    client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
    # Ensure collection exists or create it
    from qdrant_client.http.models import Distance, VectorParams
    try:
        client.get_collection(collection_name=config.QDRANT_COLLECTION_NAME)
    except Exception:
        logger.info(f"Creating Qdrant collection: {config.QDRANT_COLLECTION_NAME}")
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=embeddings.client.embedding_ctx_length, distance=Distance.COSINE),
        )
    return Qdrant(client=client, collection_name=config.QDRANT_COLLECTION_NAME, embeddings=embeddings)

knowledge_base = get_knowledge_base()

# --- Tool Definitions (Mocked for demonstration) ---

# Mock Kubernetes Client
class MockK8sClient:
    def get_pod_metrics(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        logger.info(f"MockK8sClient: Getting metrics for pod {pod_name} in {namespace}")
        # Simulate varying load for demonstration
        if "high-cpu" in pod_name:
            return {"cpu_usage_mcores": 1500, "memory_usage_mb": 512, "status": "Running"}
        if "failed-state" in pod_name:
            return {"cpu_usage_mcores": 100, "memory_usage_mb": 200, "status": "CrashLoopBackOff"}
        return {"cpu_usage_mcores": 200, "memory_usage_mb": 256, "status": "Running"}

    def restart_pod(self, namespace: str, pod_name: str) -> str:
        logger.info(f"MockK8sClient: Restarting pod {pod_name} in {namespace}")
        time.sleep(1) # Simulate operation delay
        return f"Pod {pod_name} in {namespace} successfully restarted."

    def scale_deployment(self, namespace: str, deployment_name: str, replicas: int) -> str:
        logger.info(f"MockK8sClient: Scaling deployment {deployment_name} in {namespace} to {replicas} replicas")
        time.sleep(2)
        return f"Deployment {deployment_name} in {namespace} scaled to {replicas} replicas."

    def get_deployment_info(self, namespace: str, deployment_name: str) -> Dict[str, Any]:
        logger.info(f"MockK8sClient: Getting info for deployment {deployment_name} in {namespace}")
        # Simulate deployment info
        if "nginx-app" in deployment_name:
            return {"replicas": 2, "image": "nginx:latest", "status": "Healthy"}
        return {"replicas": 1, "image": "unknown:latest", "status": "Unknown"}

mock_k8s = MockK8sClient()

# Mock Cloud Provider Client (AWS for example)
class MockAWSClient:
    def get_ec2_instance_metrics(self, instance_id: str) -> Dict[str, Any]:
        logger.info(f"MockAWSClient: Getting metrics for EC2 instance {instance_id}")
        if "i-high-cpu" in instance_id:
            return {"cpu_utilization_percent": 95, "memory_utilization_percent": 70, "status": "Running"}
        return {"cpu_utilization_percent": 20, "memory_utilization_percent": 40, "status": "Running"}

    def reboot_ec2_instance(self, instance_id: str) -> str:
        logger.info(f"MockAWSClient: Rebooting EC2 instance {instance_id}")
        time.sleep(3)
        return f"EC2 instance {instance_id} successfully rebooted."

mock_aws = MockAWSClient()

# Mock Monitoring System (Prometheus/Grafana)
class MockMonitoringSystem:
    def query_metric(self, query: str, duration_minutes: int = 5) -> List[Dict[str, Any]]:
        logger.info(f"MockMonitoringSystem: Querying metric '{query}' for last {duration_minutes} minutes")
        if "node_cpu_utilization" in query and "high" in query:
            return [{"metric": {"instance": "node-1"}, "value": [time.time(), "0.95"]}]
        if "pod_cpu_usage" in query and "high-cpu-pod" in query:
            return [{"metric": {"pod": "high-cpu-pod"}, "value": [time.time(), "1.5"]}]
        return []

mock_monitoring = MockMonitoringSystem()

# Mock Communication System (Slack)
class MockSlackClient:
    def send_message(self, channel: str, message: str) -> str:
        logger.info(f"MockSlackClient: Sending message to channel {channel}: {message}")
        return f"Message sent to {channel}."

mock_slack = MockSlackClient()

# --- InfraPilot Tools ---
@tool
def get_k8s_pod_metrics(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Gets CPU, memory usage, and status for a specified Kubernetes pod."""
    return mock_k8s.get_pod_metrics(namespace, pod_name)

@tool
def restart_k8s_pod(namespace: str, pod_name: str) -> str:
    """Restarts a specified Kubernetes pod. Use this for transient issues or to clear a bad state."""
    return mock_k8s.restart_pod(namespace, pod_name)

@tool
def scale_k8s_deployment(namespace: str, deployment_name: str, replicas: int) -> str:
    """Scales a Kubernetes deployment to a specified number of replicas. Use this for load-related issues."""
    return mock_k8s.scale_deployment(namespace, deployment_name, replicas)

@tool
def get_k8s_deployment_info(namespace: str, deployment_name: str) -> Dict[str, Any]:
    """Gets detailed information about a Kubernetes deployment including current replicas and image."""
    return mock_k8s.get_deployment_info(namespace, deployment_name)

@tool
def query_monitoring_system(query: str, duration_minutes: int = 5) -> List[Dict[str, Any]]:
    """Queries the monitoring system (e.g., Prometheus) for metric data. Provide a valid PromQL-like query string and optionally a duration in minutes. Example: 'node_cpu_utilization{instance="my-node"}'"""
    return mock_monitoring.query_metric(query, duration_minutes)

@tool
def get_aws_ec2_metrics(instance_id: str) -> Dict[str, Any]:
    """Gets CPU and memory utilization for a specified AWS EC2 instance."""
    return mock_aws.get_ec2_instance_metrics(instance_id)

@tool
def reboot_aws_ec2_instance(instance_id: str) -> str:
    """Reboots a specified AWS EC2 instance. Use for unresponsive instances."""
    return mock_aws.reboot_ec2_instance(instance_id)

@tool
def send_slack_message(channel: str, message: str) -> str:
    """Sends a message to a specified Slack channel. Use for escalating issues or providing updates."""
    return mock_slack.send_message(channel, message)

@tool
def learn_from_incident(incident_summary: str, remediation_steps: str, outcome: str) -> str:
    """Stores knowledge about a resolved incident, its remediation, and outcome in the persistent knowledge base to aid future diagnostics. This is crucial for InfraPilot's learning and adaptation."""
    content = f"Incident Summary: {incident_summary}\nRemediation Steps: {remediation_steps}\nOutcome: {outcome}"
    metadata = {"type": "incident_resolution", "timestamp": time.time()}
    knowledge_base.add_texts([content], metadatas=[metadata])
    return "Incident knowledge stored successfully."

@tool
def search_knowledge_base(query: str) -> List[Dict[str, Any]]:
    """Searches the persistent knowledge base for relevant past incidents, runbooks, or remediation strategies based on a query."""
    docs = knowledge_base.similarity_search(query, k=3)
    return [{"content": doc.page_content, "metadata": doc.metadata} for doc in docs]

# Collect all tools
infra_pilot_tools = [
    get_k8s_pod_metrics,
    restart_k8s_pod,
    scale_k8s_deployment,
    get_k8s_deployment_info,
    query_monitoring_system,
    get_aws_ec2_metrics,
    reboot_aws_ec2_instance,
    send_slack_message,
    learn_from_incident,
    search_knowledge_base
]

# --- Agent Prompt Templates ---
ORCHESTRATOR_PROMPT = PromptTemplate.from_template(
    """You are InfraPilot, an autonomous operations agent designed to detect, diagnose, and resolve cloud infrastructure incidents.
    Your primary goal is to maintain the stability and performance of systems with minimal human intervention.

    You have access to the following tools:
    {tools}

    Use the following format for your responses:
    Thought: You should always think about what to do.
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I have gathered enough information and performed necessary actions. I will now provide the final answer.
    Final Answer: A summary of the incident, actions taken, and the current status or next steps.

    Begin! Remember to be persistent and try different approaches if an action fails. Prioritize gathering information before acting.
    If you need to escalate, send a Slack message with a clear summary.

    Previous conversation history:
    {chat_history}

    Current incident/request: {input}
    """
)

# --- Main InfraPilot Orchestrator ---
class InfraPilotOrchestrator:
    def __init__(self):
        logger.info("Initializing InfraPilot Orchestrator...")
        self.memory = ConversationBufferWindowMemory(
            memory_key="chat_history", return_messages=True, input_key="input", k=config.MEMORY_WINDOW_SIZE
        )

        self.agent = create_react_agent(llm, infra_pilot_tools, ORCHESTRATOR_PROMPT)
        self.agent_executor = AgentExecutor(
            agent=self.agent, 
            tools=infra_pilot_tools, 
            verbose=True, 
            handle_parsing_errors=True, 
            memory=self.memory,
            max_iterations=15 # Prevent infinite loops
        )
        logger.info("InfraPilot Orchestrator initialized.")

    def handle_incident(self, incident_description: str) -> Dict[str, Any]:
        logger.info(f"Handling new incident: {incident_description}")
        try:
            result = self.agent_executor.invoke({"input": incident_description})
            final_answer = result.get("output", "No final answer provided.")
            logger.info(f"Incident handling complete. Final Answer: {final_answer}")
            return {"status": "resolved", "details": final_answer}
        except Exception as e:
            logger.error(f"Error handling incident: {e}", exc_info=True)
            # Attempt to send an alert if the orchestrator itself fails badly
            try:
                send_slack_message("incident-channel", f"InfraPilot experienced an error while handling incident '{incident_description}'. Error: {str(e)}. Human intervention required.")
            except Exception as slack_e:
                logger.error(f"Failed to send Slack error message: {slack_e}")
            return {"status": "failed", "details": str(e)}

    def run_continuous_monitoring_loop(self, interval_seconds: int = 60):
        logger.info(f"Starting continuous monitoring loop, checking every {interval_seconds} seconds.")
        while True:
            # This is a placeholder for real monitoring integrations (e.g., webhook listener)
            logger.info("Monitoring loop: Checking for new alerts...")
            # Simulate receiving an alert
            # In a real system, this would come from Prometheus Alertmanager, CloudWatch, etc.
            # For demo purposes, we'll just wait and potentially trigger a simulated incident.
            # This function would ideally be triggered by an external event/webhook, not polled.
            time.sleep(interval_seconds)

            # Example: Check for a specific condition every now and then
            if time.time() % 300 < interval_seconds: # Every 5 minutes, simulate a high CPU pod alert
                logger.warning("Simulating a high CPU alert for 'high-cpu-pod'...")
                self.handle_incident("Kubernetes pod 'high-cpu-pod' in namespace 'default' is experiencing consistently high CPU utilization (over 90% for 5 minutes).")

# Example usage for testing/development (not part of the main class itself)
if __name__ == "__main__":
    # Set dummy API key for testing if not set in environment
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        logger.warning("OPENAI_API_KEY not set. Using dummy key. Please set a real key for actual use.")

    # Ensure Qdrant is running or handle connection errors
    try:
        # Attempt to connect to Qdrant to ensure it's up
        client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
        client.get_collections()
        logger.info("Successfully connected to Qdrant.")
    except Exception as e:
        logger.error(f"Could not connect to Qdrant at {config.QDRANT_HOST}:{config.QDRANT_PORT}. Please ensure Qdrant is running. Error: {e}")
        logger.info("InfraPilot cannot start without a functional knowledge base. Exiting.")
        exit(1)

    pilot = InfraPilotOrchestrator()

    # Example 1: High CPU pod incident
    logger.info("\n--- Initiating Incident: High CPU Pod ---")
    incident_1 = "Kubernetes pod 'high-cpu-pod' in namespace 'default' is experiencing consistently high CPU utilization (over 90% for 5 minutes)."
    result_1 = pilot.handle_incident(incident_1)
    print(f"\nIncident 1 Result: {json.dumps(result_1, indent=2)}")

    # Example 2: Non-existent pod (should lead to diagnosis and escalation)
    logger.info("\n--- Initiating Incident: Non-Existent Pod ---")
    incident_2 = "Kubernetes pod 'non-existent-pod' in namespace 'dev' is reporting errors and is unreachable."
    result_2 = pilot.handle_incident(incident_2)
    print(f"\nIncident 2 Result: {json.dumps(result_2, indent=2)}")

    # Example 3: AWS EC2 instance issue
    logger.info("\n--- Initiating Incident: AWS EC2 High CPU ---")
    incident_3 = "AWS EC2 instance 'i-high-cpu-instance' is showing 95% CPU utilization and services are slow."
    result_3 = pilot.handle_incident(incident_3)
    print(f"\nIncident 3 Result: {json.dumps(result_3, indent=2)}")

    # Optionally, run the continuous loop (this will block)
    # logger.info("\n--- Starting continuous monitoring loop (Ctrl+C to stop) ---")
    # pilot.run_continuous_monitoring_loop(interval_seconds=30)
