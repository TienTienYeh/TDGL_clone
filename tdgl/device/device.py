import os
import logging
from operator import itemgetter
from contextlib import contextmanager, nullcontext
from typing import Optional, Sequence, Union, List, Tuple, Dict, Any
import warnings

import h5py
import pint
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch

from . import mesh
from ..units import ureg
from .components import Layer, Polygon
from .._core.mesh.mesh import Mesh

logger = logging.getLogger(__name__)


class Device:
    """An object representing a device composed of multiple layers of
    thin film superconductor.

    Args:
        name: Name of the device.
        layer: The ``Layer`` making up the device.
        film: The ``Polygon`` representing the superconducting film.
        holes: ``Polygons`` representing holes in the superconducting film.
        abstract_regions: ``Polygons`` representing abstract regions in a device.
            Abstract regions are areas that can be meshed, but need not correspond
            to any physical structres in the device.
        source_terminal: A ``Polygon`` representing the current source terminal.
            Any points that are on the boundary of the mesh and lie inside the
            source terminal will have current source boundary conditions.
        drain_terminal: A ``Polygon`` representing the current drain terminal.
            Any points that are on the boundary of the mesh and lie inside the
            drain terminal will have current drain boundary conditions.
        voltage_points: A shape ``(2, 2)`` sequence of floats, with each row
            representing the ``(x, y)`` position of a voltage probe.
        length_units: Distance units for the coordinate system.
        solve_dtype: The floating point data type to use when solving the device.
    """

    ureg = ureg

    def __init__(
        self,
        name: str,
        *,
        layer: Layer,
        film: Polygon,
        holes: Optional[List[Polygon]] = None,
        abstract_regions: Optional[List[Polygon]] = None,
        source_terminal: Optional[Polygon] = None,
        drain_terminal: Optional[Polygon] = None,
        voltage_points: Sequence[float] = None,
        length_units: str = "um",
        solve_dtype: Union[str, np.dtype] = "float64",
    ):
        self.name = name
        self.layer = layer
        self.film = film
        self.holes = holes or []
        self.abstract_regions = abstract_regions or []
        self.source_terminal = source_terminal
        self.drain_terminal = drain_terminal
        if voltage_points is not None:
            voltage_points = np.asarray(voltage_points).squeeze()
            if voltage_points.shape != (2, 2):
                raise ValueError(
                    f"Voltage points must have shape (2, 2), "
                    f"got {voltage_points.shape}."
                )
        self.voltage_points = voltage_points

        if self.source_terminal is not None:
            for terminal in [self.source_terminal, self.drain_terminal]:
                terminal.mesh = False
            if self.source_terminal.name is None:
                self.source_terminal.name = "source"
            if self.drain_terminal.name is None:
                self.drain_terminal.name = "drain"

        # Make units a "read-only" attribute.
        # It should never be changed after instantiation.
        self._length_units = length_units
        self.solve_dtype = solve_dtype

        self.mesh = None

    @property
    def length_units(self) -> str:
        """Length units used for the device geometry."""
        return self._length_units

    @property
    def solve_dtype(self) -> np.dtype:
        """Numpy dtype to use for floating point numbers."""
        return self._solve_dtype

    @solve_dtype.setter
    def solve_dtype(self, dtype) -> None:
        try:
            _ = np.finfo(dtype)
        except ValueError as e:
            raise ValueError(f"Invalid float dtype: {dtype}") from e
        self._solve_dtype = np.dtype(dtype)

    @property
    def coherence_length(self) -> float:
        return self.layer._coherence_length

    @coherence_length.setter
    def coherence_length(self, value: float) -> None:
        old_value = self.layer._coherence_length
        logger.debug(
            f"Updating coherence length from "
            f"{old_value:.3f} to {value:.3f} {self.length_units}."
        )
        if self.mesh is None:
            self.layer._coherence_length = value
            return
        logger.debug(
            f"Rebuilding the dimensionless mesh with "
            f"coherence length = {value:.3f} {self.length_units}."
        )
        # Get points in {length_units}.
        points = self.points
        triangles = self.triangles
        self.layer._coherence_length = value
        self.mesh = self._create_dimensionless_mesh(points, triangles)

    @property
    def kappa(self) -> float:
        """The Ginzburg-Landau parameter."""
        return self.layer.london_lambda / self.coherence_length

    @property
    def Bc2(self) -> pint.Quantity:
        """Upper critical field."""
        xi_ = self.coherence_length * ureg(self.length_units)
        return (ureg("Phi_0") / (2 * np.pi * xi_**2)).to_base_units()

    @property
    def A0(self) -> pint.Quantity:
        """Scale for the magnetic vector potential."""
        return self.Bc2 * self.coherence_length * self.ureg(self.length_units)

    @property
    def K0(self) -> pint.Quantity:
        """Sheet current density scale (dimensions of current / length)."""
        length_units = ureg(self.length_units)
        xi = self.coherence_length * length_units
        Lambda = self.layer.Lambda * length_units
        # e = ureg("elementary_charge")
        # Phi_0 = ureg("Phi_0")
        mu_0 = ureg("mu_0")
        K0 = 4 * xi * self.Bc2 / (mu_0 * Lambda)
        # K0 = 4 * ureg("hbar") / (2 * mu_0 * e * xi * lambda_**2 / d)
        # K0 = 4 * Phi_0 / (2 * np.pi * mu_0 * xi * lambda_**2 / d)
        # K0 = 4 * np.pi * Phi_0 / (2 * np.pi * mu_0 * xi * lambda_**2 / d)
        return K0.to_base_units()

    @property
    def terminals(self) -> Tuple[Polygon, ...]:
        if self.source_terminal is None:
            return tuple()
        return (self.source_terminal, self.drain_terminal)

    @property
    def polygons(self) -> Tuple[Polygon, ...]:
        return (
            self.terminals
            + (self.film,)
            + tuple(self.holes)
            + tuple(self.abstract_regions)
        )

    @property
    def points(self) -> Optional[np.ndarray]:
        if self.mesh is None:
            return None
        return self.coherence_length * np.array([self.mesh.x, self.mesh.y]).T

    @property
    def triangles(self) -> Optional[np.ndarray]:
        if self.mesh is None:
            return None
        return self.mesh.elements

    @property
    def edges(self) -> Optional[np.ndarray]:
        if self.mesh is None:
            return None
        return self.mesh.edge_mesh.edges

    @property
    def edge_lengths(self) -> Optional[np.ndarray]:
        """An array of the mesh vertex-to-vertex distances."""
        if self.mesh is None:
            return None
        return self.mesh.edge_mesh.edge_lengths * self.coherence_length

    @property
    def poly_points(self) -> np.ndarray:
        """Shape (n, 2) array of (x, y) coordinates of all Polygons in the Device."""
        points = np.concatenate(
            [self.film.points]
            + [poly.points for poly in self.abstract_regions if poly.mesh],
            axis=0,
        )
        # Remove duplicate points to avoid meshing issues.
        # If you don't do this and there are duplicate points,
        # meshpy.triangle will segfault.
        _, ix = np.unique(points, return_index=True, axis=0)
        points = points[np.sort(ix)]
        return points

    def copy(self) -> "Device":
        """Copy this Device to create a new one.

        Note that the new Device is returned without a mesh.

        Returns:
            A new Device instance, copied from self.
        """
        holes = [hole.copy() for hole in self.holes]
        abstract_regions = [region.copy() for region in self.abstract_regions]
        if self.source_terminal is None:
            source = drain = None
        else:
            source = self.source_terminal.copy()
            drain = self.drain_terminal.copy()
        if self.voltage_points is None:
            voltage_points = None
        else:
            voltage_points = self.voltage_points.copy()

        device = Device(
            self.name,
            layer=self.layer.copy(),
            film=self.film.copy(),
            holes=holes,
            abstract_regions=abstract_regions,
            source_terminal=source,
            drain_terminal=drain,
            voltage_points=voltage_points,
            length_units=self.length_units,
            solve_dtype=self.solve_dtype,
        )
        return device

    def _warn_if_mesh_exist(self, method: str) -> None:
        if self.mesh is not None:
            message = (
                f"Calling device.{method} on a device whose mesh already exists "
                f"returns a new device with no mesh. Call new_device.make_mesh() "
                f"to generate the mesh for the new device."
            )
            logger.warning(message)

    def scale(
        self, xfact: float = 1, yfact: float = 1, origin: Tuple[float, float] = (0, 0)
    ) -> "Device":
        """Returns a new device with polygons scaled horizontally and/or vertically.

        Negative ``xfact`` (``yfact``) can be used to reflect the device horizontally
        (vertically) about the ``origin``.

        Args:
            xfact: Factor by which to scale the device horizontally.
            yfact: Factor by which to scale the device vertically.
            origin: (x, y) coorindates of the origin.

        Returns:
            The scaled ``Device``.
        """
        if not (
            isinstance(origin, tuple)
            and len(origin) == 2
            and all(isinstance(val, (int, float)) for val in origin)
        ):
            raise TypeError("Origin must be a tuple of floats (x, y).")
        self._warn_if_mesh_exist("scale()")
        device = self.copy()
        for polygon in device.polygons:
            polygon.scale(xfact=xfact, yfact=yfact, origin=origin, inplace=True)
        return device

    def rotate(self, degrees: float, origin: Tuple[float, float] = (0, 0)) -> "Device":
        """Returns a new device with polygons rotated a given amount
        counterclockwise about specified origin.

        Args:
            degrees: The amount by which to rotate the polygons.
            origin: (x, y) coorindates of the origin.

        Returns:
            The rotated ``Device``.
        """
        if not (
            isinstance(origin, tuple)
            and len(origin) == 2
            and all(isinstance(val, (int, float)) for val in origin)
        ):
            raise TypeError("Origin must be a tuple of floats (x, y).")
        self._warn_if_mesh_exist("rotate()")
        device = self.copy()
        for polygon in device.polygons:
            polygon.rotate(degrees, origin=origin, inplace=True)
        return device

    def mirror_layer(self, about_z: float = 0.0) -> "Device":
        """Returns a new device with its layers mirrored about the plane
        ``z = about_z``.

        Args:
            about_z: The z-position of the plane (parallel to the x-y plane)
                about which to mirror the layers.

        Returns:
            The mirrored ``Device``.
        """
        device = self.copy()
        device.layer.z0 = about_z - device.layer.z0
        return device

    def translate(
        self,
        dx: float = 0,
        dy: float = 0,
        dz: float = 0,
        inplace: bool = False,
    ) -> "Device":
        """Translates the device polygons, layers, and mesh in space by a given amount.

        Args:
            dx: Distance by which to translate along the x-axis.
            dy: Distance by which to translate along the y-axis.
            dz: Distance by which to translate layers along the z-axis.
            inplace: If True, modifies the device (``self``) in-place and returns None,
                otherwise, creates a new device, translates it, and returns it.

        Returns:
            The translated device.
        """
        if inplace:
            device = self
        else:
            self._warn_if_mesh_exist("translate(..., inplace=False)")
            device = self.copy()
        for polygon in device.polygons:
            polygon.translate(dx, dy, inplace=True)
        if device.mesh is not None:
            points = device.points
            points += np.array([[dx, dy]])
            device.mesh = device._create_dimensionless_mesh(points, device.triangles)
        if dz:
            device.layer.z0 += dz
        return device

    @contextmanager
    def translation(self, dx: float, dy: float, dz: float = 0) -> None:
        """A context manager that temporarily translates a device in-place,
        then returns it to its original position.

        Args:
            dx: Distance by which to translate polygons along the x-axis.
            dy: Distance by which to translate polygons along the y-axis.
            dz: Distance by which to translate layers along the z-axis.
        """
        try:
            self.translate(dx, dy, dz=dz, inplace=True)
            yield
        finally:
            self.translate(-dx, -dy, dz=-dz, inplace=True)

    def make_mesh(
        self,
        max_edge_length: Optional[float] = None,
        optimesh_steps: Optional[int] = None,
        optimesh_method: str = "cvt-block-diagonal",
        optimesh_tolerance: float = 1e-3,
        optimesh_verbose: bool = False,
        **meshpy_kwargs,
    ) -> None:
        """Generates and optimizes the triangular mesh.

        Args:
            max_edge_length: The maximum distance between vertices in the mesh.
                Passing a value <= 0 means that the number of mesh points will be
                determined solely by the density of points in the Device's film
                and abstract regions. Defaults to 1.5 * self.coherence_length.
            optimesh_steps: Maximum number of optimesh steps. If None, then no
                optimization is done.
            optimesh_method: Name of the optimization method to use.
            optimesh_tolerance: Optimesh quality tolerance.
            optimesh_verbose: Whether to use verbose mode in optimesh.
            **meshpy_kwargs: Passed to meshpy.triangle.build().
        """
        logger.info("Generating mesh...")
        boundary = self.film.points
        if max_edge_length is None:
            max_edge_length = 1.5 * self.coherence_length
        points, triangles = mesh.generate_mesh(
            self.poly_points,
            hole_coords=[hole.points for hole in self.holes],
            max_edge_length=max_edge_length,
            boundary=boundary,
            **meshpy_kwargs,
        )
        if optimesh_steps:
            logger.info(f"Optimizing mesh with {points.shape[0]} vertices.")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=UserWarning)
                    points, triangles = mesh.optimize_mesh(
                        points,
                        triangles,
                        optimesh_steps,
                        method=optimesh_method,
                        tolerance=optimesh_tolerance,
                        verbose=optimesh_verbose,
                    )
            except np.linalg.LinAlgError as e:
                err = (
                    "LinAlgError encountered in optimesh. Try reducing min_points "
                    "or increasing the number of points in the device's important polygons."
                )
                raise RuntimeError(err) from e
        logger.info(
            f"Finished generating mesh with {points.shape[0]} points and "
            f"{triangles.shape[0]} triangles."
        )
        self.mesh = self._create_dimensionless_mesh(points, triangles)

    def _create_dimensionless_mesh(
        self, points: np.ndarray, triangles: np.ndarray
    ) -> Mesh:
        """Creates the dimensionless mesh.

        Args:
            points: Mesh vertices in ``length_units``.
            triangles: Mesh triangle indices.

        Returns:
            The dimensionless ``Mesh`` object.
        """
        if self.source_terminal is None:
            if self.drain_terminal is not None:
                raise ValueError(
                    "If source_terminal is None, drain_terminal must also be None."
                )
            input_edge = None
            output_edge = None
        else:
            if self.drain_terminal is None:
                raise ValueError(
                    "If source_terminal is not None, drain_terminal must also be"
                    " not None."
                )
            input_edge = self.source_terminal.contains_points(points, index=True)
            output_edge = self.drain_terminal.contains_points(points, index=True)

        if self.voltage_points is None:
            voltage_points = None
        else:
            voltage_points = [
                np.argmin(np.linalg.norm(points - xy, axis=1))
                for xy in self.voltage_points
            ]
            voltage_points = np.array(voltage_points)

        return Mesh.from_triangulation(
            points[:, 0] / self.coherence_length,
            points[:, 1] / self.coherence_length,
            triangles,
            input_edge=input_edge,
            output_edge=output_edge,
            voltage_points=voltage_points,
        )

    def plot(
        self,
        ax: Optional[plt.Axes] = None,
        legend: bool = True,
        figsize: Optional[Tuple[float, float]] = None,
        mesh: bool = False,
        mesh_kwargs: Dict[str, Any] = dict(color="k", lw=0.5),
        **kwargs,
    ) -> Tuple[plt.Figure, plt.Axes]:
        """Plot all of the device's polygons.

        Args:
            ax: matplotlib axis on which to plot. If None, a new figure is created.
            subplots: If True, plots each layer on a different subplot.
            legend: Whether to add a legend.
            figsize: matplotlib figsize, only used if ax is None.
            mesh: If True, plot the mesh.
            mesh_kwargs: Keyword arguments passed to ``ax.triplot()``
                if ``mesh`` is True.
            kwargs: Passed to ``ax.plot()`` for the polygon boundaries.

        Returns:
            Matplotlib Figure and Axes
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)
        else:
            fig = ax.get_figure()
        points = self.points
        if mesh:
            if self.triangles is None:
                raise RuntimeError(
                    "Mesh does not exist. Run device.make_mesh() to generate the mesh."
                )
            x = points[:, 0]
            y = points[:, 1]
            tri = self.triangles
            ax.triplot(x, y, tri, **mesh_kwargs)
        for polygon in self.polygons:
            ax = polygon.plot(ax=ax, **kwargs)
        if self.mesh is not None and self.mesh.voltage_points is not None:
            ax.plot(*points[self.mesh.voltage_points].T, "ko", label="Voltage points")
        if legend:
            ax.legend(bbox_to_anchor=(1, 1), loc="upper left")
        units = self.ureg(self.length_units).units
        ax.set_xlabel(f"$x$ $[{units:~L}]$")
        ax.set_ylabel(f"$y$ $[{units:~L}]$")
        ax.set_aspect("equal")
        return fig, ax

    def patches(self) -> Dict[str, PathPatch]:
        """Returns a dict of ``{film_name: PathPatch}``
        for visualizing the device.
        """
        abstract_regions = self.abstract_regions
        holes = self.holes
        patches = dict()
        for polygon in self.polygons:
            if polygon.name in holes:
                continue
            coords = polygon.points.tolist()
            codes = [Path.LINETO for _ in coords]
            codes[0] = Path.MOVETO
            codes[-1] = Path.CLOSEPOLY
            poly = polygon.polygon
            for hole in holes:
                if polygon.name not in abstract_regions and poly.contains(hole.polygon):
                    hole_coords = hole.points.tolist()[::-1]
                    hole_codes = [Path.LINETO for _ in hole_coords]
                    hole_codes[0] = Path.MOVETO
                    hole_codes[-1] = Path.CLOSEPOLY
                    coords.extend(hole_coords)
                    codes.extend(hole_codes)
            patches[polygon.name] = PathPatch(Path(coords, codes))
        return patches

    def draw(
        self,
        ax: Optional[plt.Axes] = None,
        legend: bool = True,
        figsize: Optional[Tuple[float, float]] = None,
        alpha: float = 0.5,
        exclude: Optional[Union[str, List[str]]] = None,
    ) -> Tuple[plt.Figure, Union[plt.Axes, np.ndarray]]:
        """Draws all polygons in the device as matplotlib patches.
        Args:
            ax: matplotlib axis on which to plot. If None, a new figure is created.
            legend: Whether to add a legend.
            figsize: matplotlib figsize, only used if ax is None.
            alpha: The alpha (opacity) value for the patches (0 <= alpha <= 1).
            exclude: A polygon name or list of polygon names to exclude
                from the figure.
        Returns:
            Matplotlib Figre and Axes.
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)
        else:
            fig = ax.get_figure()
        exclude = exclude or []
        if isinstance(exclude, str):
            exclude = [exclude]
        patches = self.patches()
        units = self.ureg(self.length_units).units
        x, y = self.poly_points.T
        margin = 0.1
        dx = np.ptp(x)
        dy = np.ptp(y)
        x0 = x.min() + dx / 2
        y0 = y.min() + dy / 2
        dx *= 1 + margin
        dy *= 1 + margin
        labels = []
        handles = []
        ax.set_aspect("equal")
        ax.grid(False)
        ax.set_xlim(x0 - dx / 2, x0 + dx / 2)
        ax.set_ylim(y0 - dy / 2, y0 + dy / 2)
        ax.set_xlabel(f"$x$ $[{units:~L}]$")
        ax.set_ylabel(f"$y$ $[{units:~L}]$")
        for i, (name, patch) in enumerate(patches.items()):
            if name in exclude:
                continue
            patch.set_alpha(alpha)
            patch.set_color(f"C{i % 10}")
            ax.add_artist(patch)
            labels.append(name)
            handles.append(patch)
        if self.mesh is not None and self.mesh.voltage_points is not None:
            (line,) = ax.plot(*self.points[self.mesh.voltage_points].T, "ko")
            handles.append(line)
            labels.append("Voltage points")
        if legend:
            ax.legend(handles, labels, bbox_to_anchor=(1, 1), loc="upper left")
        return fig, ax

    def to_hdf5(
        self,
        path_or_group: Union[str, h5py.File, h5py.Group],
        save_mesh: bool = True,
    ) -> None:
        """Serializes the Device to disk.

        Args:
            path_or_group: A path to an HDF5 file, or an open HDF5 file or group
                into which to save the ``Device``.
            save_mesh: Whether to serialize the full mesh.
        """
        if isinstance(path_or_group, str):
            path = path_or_group
            if not path.endswith(".h5"):
                path = path + ".h5"
            if os.path.exists(path):
                raise IOError(f"Path already exists: {path}.")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            save_context = h5py.File(path, "w-")
        else:
            h5_group = path_or_group
            save_context = nullcontext(h5_group)
        with save_context as f:
            f.attrs["name"] = self.name
            f.attrs["length_units"] = self.length_units
            self.layer.to_hdf5(f.create_group("layer"))
            self.film.to_hdf5(f.create_group("film"))
            if self.source_terminal is not None:
                self.source_terminal.to_hdf5(f.create_group("source_terminal"))
            if self.drain_terminal is not None:
                self.drain_terminal.to_hdf5(f.create_group("drain_terminal"))
            if self.voltage_points is not None:
                f["voltage_points"] = self.voltage_points
            for label, polygons in dict(
                holes=self.holes, abstract_regions=self.abstract_regions
            ).items():
                if polygons:
                    group = f.create_group(label)
                    for i, polygon in enumerate(polygons):
                        polygon.to_hdf5(group.create_group(str(i)))
            if save_mesh and self.mesh is not None:
                self.mesh.save_to_hdf5(f.create_group("mesh"))

    @classmethod
    def from_hdf5(cls, path_or_group: Union[str, h5py.File, h5py.Group]) -> "Device":
        """Creates a new Device from one serialized to disk.

        Args:
            path_or_group: A path to an HDF5 file, or an open HDF5 file or group
                containing the serialized Device.

        Returns:
            The loaded Device instance.
        """
        if isinstance(path_or_group, str):
            h5_context = h5py.File(path_or_group, "r")
        else:
            if not isinstance(path_or_group, (h5py.File, h5py.Group)):
                raise TypeError(
                    f"Expected an h5py.File or h5py.Group, but got "
                    f"{type(path_or_group)}."
                )
            h5_context = nullcontext(path_or_group)
        source_terminal = drain_terminal = voltage_points = None
        holes = abstract_regions = mesh = None
        with h5_context as f:
            name = f.attrs["name"]
            length_units = f.attrs["length_units"]
            layer = Layer.from_hdf5(f["layer"])
            film = Polygon.from_hdf5(f["film"])
            if "source_terminal" in f:
                source_terminal = Polygon.from_hdf5(f["source_terminal"])
            if "drain_terminal" in f:
                drain_terminal = Polygon.from_hdf5(f["drain_terminal"])
            if "holes" in f:
                holes = [
                    Polygon.from_hdf5(grp)
                    for _, grp in sorted(f["holes"].items(), key=itemgetter(0))
                ]
            if "abstract_regions" in f:
                abstract_regions = [
                    Polygon.from_hdf5(grp)
                    for _, grp in sorted(
                        f["abstract_regions"].items(), key=itemgetter(0)
                    )
                ]
            if "voltage_points" in f:
                voltage_points = np.array(f["voltage_points"])
            if "mesh" in f:
                mesh = Mesh.load_from_hdf5(f["mesh"])

        device = Device(
            name,
            layer=layer,
            film=film,
            holes=holes,
            abstract_regions=abstract_regions,
            source_terminal=source_terminal,
            drain_terminal=drain_terminal,
            voltage_points=voltage_points,
            length_units=length_units,
        )

        if mesh is not None:
            device.mesh = mesh

        return device

    def __repr__(self) -> str:
        # Normal tab "\t" renders a bit too big in jupyter if you ask me.
        indent = 4
        t = " " * indent
        nt = "\n" + t

        args = [
            f"{self.name!r}",
            f"layer={self.layer!r}",
            f"film={self.film!r}",
            f"holes={self.holes!r}",
            f"abstract_regions={self.abstract_regions!r}",
            f"source_terminal={self.source_terminal!r}",
            f"drain_terminal={self.drain_terminal!r}",
            f"voltage_points={self.voltage_points!r}",
            f"length_units={self.length_units!r}",
            f"solve_dtype={self.solve_dtype!r}",
        ]

        return f"{self.__class__.__name__}(" + nt + (", " + nt).join(args) + ",\n)"

    def __eq__(self, other) -> bool:
        if other is self:
            return True

        if not isinstance(other, Device):
            return False

        return (
            self.name == other.name
            and self.layer == other.layer
            and self.film == other.film
            and self.holes == other.holes
            and self.abstract_regions == other.abstract_regions
            and self.terminals == other.terminals
            and self.length_units == other.length_units
        )
