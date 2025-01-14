"""Run integration tests with a speckle server."""

import secrets
import string

import pytest
from gql import gql
from speckle_automate import AutomationRunData, AutomationStatus, run_function, AutomationContext
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.objects.base import Base
from specklepy.objects.geometry import Mesh
from specklepy.transports.server import ServerTransport

from main import FunctionInputs, automate_function


def crypto_random_string(length: int) -> str:
    """Generate a semi crypto random string of a given length."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def register_new_automation(
        project_id: str,
        model_id: str,
        speckle_client: SpeckleClient,
        automation_id: str,
        automation_name: str,
        automation_revision_id: str,
):
    """Register a new automation in the speckle server."""
    query = gql(
        """
        mutation CreateAutomation(
            $projectId: String! 
            $modelId: String! 
            $automationName: String!
            $automationId: String! 
            $automationRevisionId: String!
        ) {
                automationMutations {
                    create(
                        input: {
                            projectId: $projectId
                            modelId: $modelId
                            automationName: $automationName 
                            automationId: $automationId
                            automationRevisionId: $automationRevisionId
                        }
                    )
                }
            }
        """
    )
    params = {
        "projectId": project_id,
        "modelId": model_id,
        "automationName": automation_name,
        "automationId": automation_id,
        "automationRevisionId": automation_revision_id,
    }
    speckle_client.httpclient.execute(query, params)


@pytest.fixture()
def speckle_token(request) -> str:
    return request.config.SPECKLE_TOKEN


@pytest.fixture()
def speckle_server_url(request) -> str:
    """Provide a speckle server url for the test suite, default to localhost."""
    return request.config.SPECKLE_SERVER_URL


@pytest.fixture()
def test_client(speckle_server_url: str, speckle_token: str) -> SpeckleClient:
    """Initialize a SpeckleClient for testing."""
    test_client = SpeckleClient(
        speckle_server_url, speckle_server_url.startswith("https")
    )
    test_client.authenticate_with_token(speckle_token)
    return test_client


@pytest.fixture()
def test_object() -> Base:
    """Create a Base model for testing."""
    root_object = Base()
    root_object.foo = "bar"
    return root_object


@pytest.fixture()
def automation_run_data(
        test_object: Base, test_client: SpeckleClient, speckle_server_url: str
) -> AutomationRunData:
    """Set up an automation context for testing."""
    project_id = test_client.stream.create("Automate function e2e test")
    branch_name = "main"

    model = test_client.branch.get(project_id, branch_name, commits_limit=1)
    model_id: str = model.id

    root_obj_id = operations.send(
        test_object, [ServerTransport(project_id, test_client)]
    )
    version_id = test_client.commit.create(project_id, root_obj_id)

    automation_name = crypto_random_string(10)
    automation_id = crypto_random_string(10)
    automation_revision_id = crypto_random_string(10)

    register_new_automation(
        project_id,
        model_id,
        test_client,
        automation_id,
        automation_name,
        automation_revision_id,
    )

    automation_run_id = crypto_random_string(10)
    function_id = crypto_random_string(10)
    function_revision = crypto_random_string(10)
    return AutomationRunData(
        project_id=project_id,
        model_id=model_id,
        branch_name=branch_name,
        version_id=version_id,
        speckle_server_url=speckle_server_url,
        automation_id=automation_id,
        automation_revision_id=automation_revision_id,
        automation_run_id=automation_run_id,
        function_id=function_id,
        function_revision=function_revision,
        function_name=""
    )


def test_function_run(automation_run_data: AutomationRunData, speckle_token: str, sample_bases):
    """Run an integration test for the automate function."""

    context = AutomationContext.initialize(automation_run_data, speckle_token)

    automate_sdk = run_function(
        context,
        automate_function,
        FunctionInputs(density_level=1000, max_percentage_high_density_objects=0.1),
    )

    assert automate_sdk.run_status == AutomationStatus.FAILED


@pytest.fixture
def sample_bases():
    base_with_display_value = Base()
    base_with_display_value.displayValue = [Mesh()]

    base_without_display_value = Base()

    return base_with_display_value, base_without_display_value
