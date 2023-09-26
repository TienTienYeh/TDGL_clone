import numba
import numpy as np

try:
    import cupy  # type: ignore
    import cupyx  # type: ignore
except ModuleNotFoundError:
    cupy = None
    cupyx = None


@numba.njit(fastmath=True, parallel=True)
def get_A_induced_numba(
    J_site: np.ndarray,
    site_areas: np.ndarray,
    sites: np.ndarray,
    edge_centers: np.ndarray,
) -> np.ndarray:
    """Calculates the induced vector potential on the mesh edges.

    Args:
        J_site: The current density on the sites, shape ``(n, )``
        site_areas: The mesh site areas, shape ``(n, )``
        sites: The mesh site coordinates, shape ``(n, 2)``
        edge_centers: The coordinates of the edge centers, shape ``(m, 2)``

    Returns:
        The induced vector potential on the mesh edges.
    """
    assert J_site.ndim == 2
    assert J_site.shape[1] == 2
    assert sites.shape == J_site.shape
    assert edge_centers.ndim == 2
    assert edge_centers.shape[1] == 2
    out = np.empty((edge_centers.shape[0], sites.shape[1]), dtype=J_site.dtype)
    for i in numba.prange(edge_centers.shape[0]):
        for k in range(J_site.shape[1]):
            tmp = 0.0
            for j in range(J_site.shape[0]):
                dr = np.sqrt(
                    (edge_centers[i, 0] - sites[j, 0]) ** 2
                    + (edge_centers[i, 1] - sites[j, 1]) ** 2
                )
                tmp += J_site[j, k] * site_areas[j] / dr
            out[i, k] = tmp
    return out


get_A_induced_cupy = None

if cupy is not None:

    @cupyx.jit.rawkernel()
    def get_A_induced_cupy(
        J_site: cupy.ndarray,
        site_areas: cupy.ndarray,
        sites: cupy.ndarray,
        edge_centers: cupy.ndarray,
        A_induced: cupy.ndarray,
    ) -> None:
        """Calculates the induced vector potential on the mesh edges.

        Args:
            J_site: The current density on the sites, shape ``(n, )``
            site_areas: The mesh site areas, shape ``(n, )``
            sites: The mesh site coordinates, shape ``(n, 2)``
            edge_centers: The coordinates of the edge centers, shape ``(m, 2)``
            A_induced: The induced vector potential on the mesh edges,
                i.e. the output array, shape ``(m, 2)``.
        """
        i, k = cupyx.jit.grid(2)
        if i < edge_centers.shape[0] and k < J_site.shape[1]:
            tmp = 0.0
            for j in cupyx.jit.range(sites.shape[0]):
                dr = cupy.sqrt(
                    (edge_centers[i, 0] - sites[j, 0]) ** 2
                    + (edge_centers[i, 1] - sites[j, 1]) ** 2
                )
                tmp += J_site[j, k] * site_areas[j] / dr
            A_induced[i, k] = tmp
