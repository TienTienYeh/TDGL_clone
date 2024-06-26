.. py-tdgl

.. _api-visualization:


*************
Visualization
*************

CLI tool: ``tdgl.visualize``
----------------------------

``tdgl.visualize`` is a command line interface (CLI) for animating and interactively viewing the
time- and space-dependent results of TDGL simulations.

.. argparse::
    :module: tdgl.visualize
    :func: make_parser
    :prog: python -m tdgl.visualize

Create animations
-----------------

.. autofunction:: tdgl.visualization.create_animation


Plot ``Solutions``
------------------

.. seealso::

    :meth:`tdgl.Solution.plot_currents`, :meth:`tdgl.Solution.plot_order_parameter`,
    :meth:`tdgl.Solution.plot_field_at_positions`, :meth:`tdgl.Solution.plot_scalar_potential`
    :meth:`tdgl.Solution.plot_vorticity`

.. autofunction:: tdgl.plot_currents

.. autofunction:: tdgl.plot_order_parameter

.. autofunction:: tdgl.plot_field_at_positions

.. autofunction:: tdgl.plot_vorticity

.. autofunction:: tdgl.plot_scalar_potential

.. autofunction:: tdgl.plot_current_through_paths

Plotting utilities
------------------

.. autofunction:: tdgl.visualization.convert_to_xdmf

.. autofunction:: tdgl.visualization.auto_range_iqr

.. autofunction:: tdgl.visualization.auto_grid

.. autofunction:: tdgl.non_gui_backend

