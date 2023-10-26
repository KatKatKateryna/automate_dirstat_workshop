import statistics
from dataclasses import dataclass, field

from matplotlib import pyplot as plt
from speckle_automate import AutomationContext
from specklepy.objects.base import Base
from specklepy.objects.geometry import Mesh
from typing import Optional, TypeVar, List, Dict, Union

from specklepy.objects.other import RenderMaterial
from specklepy.objects.primitive import Interval

from Utilities.utilities import Utilities

T = TypeVar("T", bound=Base)


@dataclass
class HealthObject:
    """Data structure representing the health of a Speckle object.

    This class captures various metrics of a Speckle object, including size,
    area, volume, and density. It also captures the type of the parent object
    in the Speckle object hierarchy.
    """

    id: str
    sizes: Dict[str, int] = field(default_factory=dict)  # Size of the object in bytes
    bounding_volumes: Dict[str, float] = field(default_factory=dict)
    areas: Dict[str, float] = field(default_factory=dict)
    parent_type: Optional[str] = None  # Type of the parent Speckle object
    speckle_type: Optional[str] = None  # Type of the Speckle object
    display_values: List[T] = field(default_factory=list)
    units: str = None
    dimension: str = "3D"
    render_material: Optional[RenderMaterial] = None

    def __repr__(self):
        entries = []
        for key in self.sizes:
            size = self.sizes.get(key, 0)
            density = self.densities.get(key, 0)
            volume = self.bounding_volumes.get(key, 0)
            area = self.areas.get(key, 0)
            dimension = self.dimension
            entries.append(
                f"{key}: (dimension={dimension}, size={size}, volume={volume}, area={area}, density={density})"
            )

        entries_str = ", ".join(entries)
        return (
            f"HealthObject(id={self.id!r}, parent_type={self.parent_type!r}, "
            f"entries={{{entries_str}}})"
        )

    @property
    def densities(self) -> Dict[str, float]:
        """Compute the density of each object.

        Density is defined as:
        - For all objects: size divided by the area.
        If the area is zero, density defaults to zero.
        """
        return {
            key: (self.sizes[key] / self.areas[key]) if self.areas[key] != 0 else 0
            for key in self.sizes
        }

    @property
    def aggregate_density(self) -> float:
        """Compute the aggregate density of the object.

        Aggregate density is defined as the sum of all sizes divided by the sum of all areas. If the total area is zero, density defaults to zero.
        """
        total_size = sum(self.sizes.values())
        total_area = sum(self.areas.values())
        return total_size / total_area if total_area != 0 else 0

    def convert_from_base(self, base_object: Base) -> None:
        """Populate the HealthObject attributes from a Speckle Base object.

        Args:
            base_object (Base): The Speckle Base object to convert from.

        Raises:
            ValueError: If no bounding volume information is found for the object.
        """
        self.id = base_object.id
        self.parent_type = getattr(
            base_object, "parent_type", None
        )  # Fetch the parent_type attribute
        self.speckle_type = base_object.speckle_type
        self.units = base_object.units
        display_value = Utilities.try_get_display_value(base_object)

        if display_value:
            self.compute_bounding_volume_from_display_values(display_value)

        if display_value:
            self.display_values = display_value
            self.compute_byte_size_from_display_values(display_value)

    def compute_bounding_volume_from_display_values(
        self, display_value: List[T]
    ) -> None:
        """Compute volume from a mesh representation.

        Currently, this is a placeholder and returns 0. Actual volume
        computation logic can be added in the future.

        Args:
            display_value: The representation(s) of the object.

        Returns:
            float: The computed volume.
        """
        for index, dv in enumerate(display_value):
            if hasattr(dv, "bbox") and dv.bbox:
                self.bounding_volumes[dv.id] = dv.bbox.volume
            elif isinstance(dv, Mesh):
                x_interval = self.interval_from_coordinates_by_offset(dv.vertices, 0)
                y_interval = self.interval_from_coordinates_by_offset(dv.vertices, 1)
                z_interval = self.interval_from_coordinates_by_offset(dv.vertices, 2)

                self.bounding_volumes[dv.id] = (
                    x_interval.length() * y_interval.length() * z_interval.length()
                )
                self.bounding_volumes[dv.id] /= 1000000000  # Convert to m^3

                self.areas[dv.id] = (
                    x_interval.length() * y_interval.length()
                ) / 1000000

                if z_interval.length() == 0:
                    self.dimension = "2D"

            else:
                self.bounding_volumes[
                    dv.id
                ] = 0.0  # TODO: Handle other types of display values

    def compute_byte_size_from_display_values(self, display_values: List[T]) -> None:
        """Compute the byte size of a list of display values.

        Args:
            display_values (List[T]): A list of display values.

        Returns:
            int: The computed byte size.
        """

        self.sizes.update({dv.id: Utilities.get_byte_size(dv) for dv in display_values})

    @staticmethod
    def interval_from_coordinates_by_offset(
        vertices: List[float], offset: int = 0
    ) -> Interval:
        """Compute interval from coordinates by offset.

        Args:
            vertices (List[float]): List of vertex coordinates.
            offset (int, optional): Offset to start from. Defaults to 0.

        Returns:
            Interval: Computed interval.
        """
        axis_coordinates = vertices[offset::3]
        axis_interval = Interval(start=min(axis_coordinates), end=max(axis_coordinates))
        return axis_interval


def colorise_densities(
    automate_context: AutomationContext, health_objects: Dict[str, HealthObject]
) -> None:
    """
    Create a color gradient based on density values for visualization.

    Args:
        automate_context (AutomationContext): Context for the automate function.
        health_objects (Dict[str, HealthObject]): Dictionary mapping object IDs
                                                  to their HealthObject.

    For each HealthObject, this function calculates a color based on its
    density. This color then is used to update the object's render material.
    """

    # Extracting densities for each HealthObject
    densities = {ho.id: ho.aggregate_density for ho in health_objects.values()}

    if len(densities.items()) == 0:
        return

    # Determine the range of densities for normalization
    min_density = min(densities.values())
    max_density = max(densities.values())

    # Get the colormap and normalize the densities
    cmap = plt.get_cmap("viridis")
    norm = plt.Normalize(min_density, max_density)

    # Iterate through each HealthObject and update its render material
    for obj_id, density in densities.items():
        rgba_color = cmap(norm(density))

        # Convert RGBA to Hex
        hex_color = "#{:02x}{:02x}{:02x}".format(
            int(rgba_color[0] * 255), int(rgba_color[1] * 255), int(rgba_color[2] * 255)
        )

        # Convert hex color to ARBG integer format
        arbg_color = int(hex_color[1:], 16) - (1 << 32)

        # Attach color information for visualization
        automate_context.attach_info_to_objects(
            category="Density Visualization",
            metadata={"density": density},
            message="density visualization",
            object_ids=obj_id,
            visual_overrides={"color": hex_color},
        )

        # Update the render material of the HealthObject
        health_objects[obj_id].render_material = RenderMaterial(diffuse=arbg_color)


def attach_visual_markers(
    automate_context: AutomationContext,
    health_objects: Dict[str, HealthObject],
    density_level: float,
) -> None:
    """
    Attach visual markers and notifications based on density.

    Args:
        automate_context: Context for the automate function.
        health_objects: Dictionary of health objects.
        density_level: Threshold for high density.
    """
    for ho in health_objects.values():
        if any(value > density_level for value in ho.densities.values()):
            count_exceeding = sum(
                1 for value in ho.densities.values() if value > density_level
            )
            automate_context.attach_error_to_objects(
                category="Density Check",
                object_ids=ho.id,
                message=(
                    f"{count_exceeding} mesh{'es' if count_exceeding != 1 else ''} "
                    f"of this object {'have' if count_exceeding != 1 else 'has'} a density, "
                    f"that exceeds the threshold of {density_level}."
                ),
                visual_overrides={"color": "#ff0000"},
            )
        else:
            automate_context.attach_info_to_objects(
                category="Density Check",
                object_ids=ho.id,
                message=f"This object has an acceptable density of {ho.aggregate_density}.",
                visual_overrides={"color": "#00ff00"},
            )


def create_health_objects(bases: List[Base]) -> Dict[str, HealthObject]:
    """
    Converts bases into health objects for further analysis.

    Args:
        bases: List of base objects.

    Returns:
        Dictionary mapping IDs to corresponding health objects.
    """
    health_objects = {b.id: HealthObject(id=b.id) for b in bases}
    for b in bases:
        health_objects[b.id].convert_from_base(b)

    return health_objects


def density_summary(
    health_objects: Dict[str, "HealthObject"]
) -> tuple[List[List[Union[str, float, int]]], List[float], List[int]]:
    """
    Generate a density summary for the provided health objects.

    This method filters health objects based on their areas, computes
    various statistical metrics on their densities, and prepares a summary
    table of these metrics.

    Args:
        health_objects (Dict[str, 'HealthObject']): A dictionary of health
            objects to compute the summary for.

    Returns:
        tuple: A tuple containing the summary table, all densities, and
            all areas.
    """
    # Filter objects with any area value greater than or equal to 0
    filtered_health_objects = [
        ho
        for ho in health_objects.values()
        if any(area >= 0 for area in ho.areas.values())
    ]

    # Extract relevant data
    all_densities = [ho.aggregate_density for ho in filtered_health_objects]
    all_areas = [sum(ho.bounding_volumes.values()) for ho in filtered_health_objects]

    # Compute statistical metrics
    count = len(filtered_health_objects)
    avg_density = round(sum(all_densities) / count if count else 0, 3)
    median_density = round(statistics.median(all_densities), 3)
    max_density = round(max(all_densities), 3)
    min_density = round(min(all_densities), 3)
    std_dev_density = round(statistics.stdev(all_densities) if count > 1 else 0, 3)
    q1_density = round(statistics.quantiles(all_densities, n=4)[0], 3)
    q3_density = round(statistics.quantiles(all_densities, n=4)[2], 3)

    # Prepare the summary table
    data = [
        ["Metric", "Value"],
        ["Count", count],
        ["Average Density", avg_density],
        ["Median Density", median_density],
        ["Max Density", max_density],
        ["Min Density", min_density],
        ["Standard Deviation", std_dev_density],
        ["First Quartile", q1_density],
        ["Third Quartile", q3_density],
    ]

    return data, all_densities, all_areas


def createColoredMeshes(
    automate_context: AutomationContext, health_objects: Dict[str, HealthObject]
) -> Base:
    return Base()
