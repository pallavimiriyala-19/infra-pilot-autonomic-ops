import os
import time
import json
import logging
from infra_pilot.orchestrator import InfraPilotOrchestrator, config
from qdrant_client import QdrantClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_mock_environment():
    """Sets up necessary environment variables for the example if not already present."""
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-test-key-for-infra-pilot" # Use a dummy key for local testing
        logger.warning("OPENAI_API_KEY not set. Using a dummy key for demonstration. Please set a real key for actual use.")
    
    # Ensure Qdrant host/port are set for the example
    os.environ.setdefault("QDRANT_HOST", "localhost")
    os.environ.setdefault("QDRANT_PORT", "6333")
    os.environ.setdefault("QDRANT_COLLECTION_NAME", "infra_pilot_example_knowledge")

def check_qdrant_connection():
    """Attempts to connect to Qdrant to verify its availability."""
    try:
        client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
        client.get_collections()
        logger.info(f"Successfully connected to Qdrant at {config.Qdrant_HOST}:{config.Qdrant_PORT}.")
        return True
    except Exception as e:
        logger.error(f"Could not connect to Qdrant at {config.Qdrant_HOST}:{config.Qdrant_PORT}. Please ensure Qdrant is running. Error: {e}")
        logger.info("InfraPilot requires Qdrant for its knowledge base. Exiting.")
        return False

if __name__ == "__main__":
    setup_mock_environment()
    
    if not check_qdrant_connection():
        exit(1)

    pilot = InfraPilotOrchestrator()
    
    logger.info("\n=======================================================")
    logger.info("InfraPilot Example Usage: Simulating Cloud Incidents")
    logger.info("=======================================================\n")

    # --- Scenario 1: Kubernetes Pod High CPU --- 
    logger.info("--- Scenario 1: Kubernetes Pod High CPU Anomaly ---")
    incident_description_1 = "Kubernetes pod 'high-cpu-app-pod' in namespace 'default' is reporting consistently high CPU utilization (over 90% for 10 minutes) and users are experiencing latency."
    logger.info(f"InfraPilot receives: {incident_description_1}")
    result_1 = pilot.handle_incident(incident_description_1)
    print(f"\n>>> InfraPilot Response for Scenario 1:\n{json.dumps(result_1, indent=2)}\n")
    time.sleep(2) # Give some breathing room

    # --- Scenario 2: Non-existent Kubernetes Resource (Diagnosis & Escalation) ---
    logger.info("--- Scenario 2: Unreachable Kubernetes Service (Non-existent Resource) ---")
    incident_description_2 = "Service 'api-gateway' in namespace 'prod' is unreachable. Monitoring shows 100% error rate for requests to it. Initial checks indicate pods might be missing or misconfigured."
    logger.info(f"InfraPilot receives: {incident_description_2}")
    result_2 = pilot.handle_incident(incident_description_2)
    print(f"\n>>> InfraPilot Response for Scenario 2:\n{json.dumps(result_2, indent=2)}\n")
    time.sleep(2)

    # --- Scenario 3: AWS EC2 Instance Under Stress --- 
    logger.info("--- Scenario 3: AWS EC2 Instance Under Stress ---")
    incident_description_3 = "AWS EC2 instance 'i-0a1b2c3d4e5f6g7h8' (web-server-prod) is showing very high CPU utilization (98%) and low memory (90% consumed). Applications on it are unresponsive."
    logger.info(f"InfraPilot receives: {incident_description_3}")
    result_3 = pilot.handle_incident(incident_description_3)
    print(f"\n>>> InfraPilot Response for Scenario 3:\n{json.dumps(result_3, indent=2)}\n")
    time.sleep(2)

    # --- Scenario 4: Learning from a simulated past incident ---
    logger.info("--- Scenario 4: Querying Knowledge Base after learning ---")
    # First, simulate adding knowledge (this would happen after a successful resolution)
    pilot.handle_incident(
        "Learn: An earlier incident with 'backend-worker' pod memory leak was resolved by increasing its memory limit and restarting. Outcome: Resolved."
    )
    print("\n(InfraPilot has 'learned' from a past incident)\n")
    
    incident_description_4 = "A new alert for 'backend-worker' pod in namespace 'default' is showing high memory usage, similar to a past incident. Can InfraPilot recall relevant past solutions?"
    logger.info(f"InfraPilot receives: {incident_description_4}")
    result_4 = pilot.handle_incident(incident_description_4)
    print(f"\n>>> InfraPilot Response for Scenario 4:\n{json.dumps(result_4, indent=2)}\n")
    time.sleep(2)

    logger.info("=======================================================")
    logger.info("InfraPilot Example Usage Complete.")
    logger.info("=======================================================")

    # Clean up Qdrant collection for the example if desired
    # try:
    #     client = QdrantClient(host=config.Qdrant_HOST, port=config.Qdrant_PORT)
    #     client.delete_collection(collection_name=config.Qdrant_COLLECTION_NAME)
    #     logger.info(f"Cleaned up Qdrant collection: {config.Qdrant_COLLECTION_NAME}")
    # except Exception as e:
    #     logger.error(f"Error cleaning up Qdrant collection: {e}")

