"""This module contains the business logic for a Speckle Automate function.

The purpose is to demonstrate how one can use the automation_context module
to process and analyze data in a Speckle project.
"""
from pydantic import Field
from speckle_automate import (
    AutomateBase,
    AutomationContext,
    execute_automate_function,
)

from Objects.objects import (
    attach_visual_markers,
    colorise_densities,
    create_health_objects,
    createColoredMeshes,
    density_summary,
)
from Utilities.reporting import Report
from Utilities.utilities import Utilities

## new render materials for objects passing/failing
## swap those into the original commit object
## send that back to the server


class FunctionInputs(AutomateBase):
    """Definition of user inputs for this function.

    These fields define the parameters that users can adjust when triggering
    this function in the Speckle web application.
    """

    density_level: float = Field(
        title="Density Threshold",
        description=(
            "Set a density value as the threshold. Objects with "
            "densities exceeding this value will be highlighted."
        ),
    )
    max_percentage_high_density_objects: float = Field(
        title="High Density Object Limit (%)",
        description=(
            "Specify the maximum percentage (0-1) of objects you're "
            "willing to allow above the set density threshold. "
            "For instance, a value of 0.1 means you'll tolerate up "
            "to 10% of the objects having a density above the threshold."
        ),
        ge=0.0,
        le=1.0,
    )


def automate_function(
    automate_context: AutomationContext, function_inputs: FunctionInputs
) -> None:
    """Analyzes Speckle data and provides visual markers and notifications.

    Fetches the specified version of the Speckle project, evaluates its objects
    based on their density, and reports results visually and as notifications.

    Args:
        automate_context (AutomationContext): Context for the current run,
            providing methods to fetch project data and send results.
        function_inputs (FunctionInputs): User-defined parameters guiding
            the analysis.
    """
    # Fetch the root object of the specified Speckle project version.
    version_root_object = automate_context.receive_version()

    # Filter out objects to keep only displayable ones with valid IDs.
    displayable_bases = Utilities.filter_displayable_bases(version_root_object)

    if not displayable_bases:
        automate_context.mark_run_failed("No displayable mesh objects found.")
        return

    # Transform filtered objects to health objects for density analysis.
    health_objects = create_health_objects(displayable_bases)

    # Attach visual cues and notifications based on object densities.
    attach_visual_markers(
        automate_context, health_objects, function_inputs.density_level
    )

    colorise_densities(automate_context, health_objects)
    colored_meshes = createColoredMeshes(automate_context, health_objects)

    # Wrap up the analysis by marking the run either successful or failed.
    pass_rate_percentage = function_inputs.max_percentage_high_density_objects
    threshold = function_inputs.density_level

    commit_details = {
        "stream_id": automate_context.automation_run_data.project_id,
        "commit_id": automate_context.automation_run_data.version_id,
        "server_url": automate_context.automation_run_data.speckle_server_url,
    }

    summary_data = Report.generate_summary(
        threshold, pass_rate_percentage, health_objects, commit_details
    )

    high_density_count = summary_data["values"]["fail_count"]
    total_displayable_count = len(displayable_bases)

    ################## generate report
    data, all_densities, all_areas = density_summary(health_objects)
    report_data = {
        "table_data": summary_data["table"],
        "result": summary_data["values"]["result"],
    }
    report = Report.generate_pdf(
        all_densities, [float(a) for a in all_areas], data, threshold, report_data
    )
    file_name = Report.write_pdf_to_temp(report)
    automate_context.store_file_result(file_name)
    ##################

    automate_context.create_new_version_in_project(
        colored_meshes,
        automate_context.automation_run_data.branch_name + "_automate_mesh_check",
    )

    if summary_data["values"]["result"] == "Fail":
        automate_context.mark_run_failed(
            f"Too many high-density objects. Allowed: "
            f"{pass_rate_percentage * 100}%, Found: "
            f"{(high_density_count / total_displayable_count) * 100}%."
        )
    else:
        automate_context.mark_run_success(
            "Analysis complete. High-density objects within acceptable limits."
        )


if __name__ == "__main__":
    # Entry point: Execute the automate function with defined inputs.
    execute_automate_function(automate_function, FunctionInputs)
