"""
defines GuiCommon

This file defines functions related to the result updating that are VTK specific
"""
# coding: utf-8
# pylint: disable=C0111
from __future__ import print_function, unicode_literals
from copy import deepcopy
from six import iteritems, itervalues, iterkeys, string_types

import numpy as np
from numpy import full, issubdtype
from numpy.linalg import norm  # type: ignore
import vtk

from pyNastran.utils import integer_types
from pyNastran.gui.gui_objects.names_storage import NamesStorage
from pyNastran.gui.qt_files.gui_attributes import GuiAttributes
from pyNastran.gui.utils.vtk.vtk_utils import numpy_to_vtk, numpy_to_vtk_points, VTK_VERSION
from pyNastran.gui import IS_DEV

WHITE = (1., 1., 1.)
BLUE = (0., 0., 1.)
RED = (1., 0., 0.)


class GuiCommon(GuiAttributes):
    def __init__(self, **kwds):
        inputs = kwds['inputs']
        kwds['res_widget'] = None
        super(GuiCommon, self).__init__(**kwds)
        self.is_groups = inputs['is_groups']

        #self.groups = set([])
        self._group_elements = {}
        self._group_coords = {}
        self._group_shown = {}
        self._names_storage = NamesStorage()

        self.vtk_version = VTK_VERSION
        print('vtk_version = %s' % (self.vtk_version))
        if self.vtk_version[0] < 7 and not IS_DEV:  # TODO: should check for 7.1
            raise RuntimeError('VTK %s is no longer supported' % vtk.VTK_VERSION)

    def update_axes_length(self, dim_max):
        """
        sets the driving dimension for:
          - picking?
          - coordinate systems
          - label size
        """
        self.settings.dim_max = dim_max
        dim = self.dim * 0.10
        self.on_set_axes_length(dim)

    def on_set_axes_length(self, dim=None):
        """
        scale coordinate system based on model length
        """
        if dim is None:
            dim = self.settings.dim_max * 0.10
        if hasattr(self, 'axes'):
            for axes in itervalues(self.axes):
                axes.SetTotalLength(dim, dim, dim)

    def update_text_actors(self, subcase_id, subtitle, min_value, max_value, label):
        """
        Updates the text actors in the lower left

        Max:  1242.3
        Min:  0.
        Subcase: 1 Subtitle:
        Label: SUBCASE 1; Static
        """
        if isinstance(max_value, integer_types):
            max_msg = 'Max:  %i' % max_value
            min_msg = 'Min:  %i' % min_value
        elif isinstance(max_value, string_types):
            max_msg = 'Max:  %s' % str(max_value)
            min_msg = 'Min:  %s' % str(min_value)
        else:
            max_msg = 'Max:  %g' % max_value
            min_msg = 'Min:  %g' % min_value
        self.text_actors[0].SetInput(max_msg)
        self.text_actors[1].SetInput(min_msg)
        self.text_actors[2].SetInput('Subcase: %s Subtitle: %s' % (subcase_id, subtitle))  # info

        if label:
            self.text_actors[3].SetInput('Label: %s' % label)  # info
            self.text_actors[3].VisibilityOn()
        else:
            self.text_actors[3].VisibilityOff()

    def on_rcycle_results(self, case=None):
        """the reverse of on_cycle_results"""
        if len(self.case_keys) <= 1:
            return

        #ncases = len(self.case_keys)
        #icasei = self.case_keys.index(self.icase)
        #icasei2 = ncases + icasei - 1
        #icase = (self.case_keys + self.case_keys)[icasei2]
        #self.cycle_results(icase)
        #self.icase = icase

        icase = self.icase - 1
        while 1:  # TODO: speed this up
            if icase == -1:
                icase = self.ncases - 1
            try:
                self.cycle_results(icase)
                break
            except IndexError:
                icase -= 1

    def on_cycle_results(self, case=None, show_msg=True):
        """the gui method for calling cycle_results"""
        if len(self.case_keys) <= 1:
            return

        #ncases = len(self.case_keys)
        #icasei = self.case_keys.index(self.icase)
        #icasei2 = icasei + 1
        #icase = (self.case_keys + self.case_keys)[icasei2]
        #self.cycle_results(icase)
        #self.icase = icase

        icase = self.icase + 1
        while 1:  # TODO: speed this up
            if icase == self.ncases:
                icase = 0
            try:
                self.cycle_results(icase, show_msg=show_msg)
                break
            except IndexError:
                icase += 1

    def cycle_results(self, case=None, show_msg=True):
        """
        Selects the next case

        Parameters
        ----------
        case : int; default=None
            selects the icase
            None : defaults to self.icase+1
        """
        #print('-----------------')
        #print('real-cycle_results(case=%r)' % case)
        if case is None:
            #print('adding 1 to case (%s)' % (self.icase))
            case = self.icase + 1

        assert case is not False, case
        ncases = len(self.case_keys)
        if ncases <= 1:
            self.log_warning('cycle_results(result_name=%r); ncases=%i' % (
                case, ncases))
            if self.ncases == 0:
                self.scalarBar.SetVisibility(False)
            return
        case = self.cycle_results_explicit(case, explicit=False, show_msg=show_msg)
        assert case is not False, case
        if show_msg:
            self.log_command('cycle_results(case=%r)' % self.icase)

    def get_subtitle_label(self, subcase_id):
        try:
            subtitle, label = self.isubcase_name_map[subcase_id]
        except TypeError:
            subtitle = 'case=NA'
            label = 'label=NA'
        except KeyError:
            subtitle = 'case=NA'
            label = 'label=NA'
        return subtitle, label

    def on_clear_results(self, show_msg=True):
        """clears the model of all results"""
        (obj, (i, name)) = self.result_cases[self.icase]
        unused_location = obj.get_location(i, name)

        unused_name_str = self._names_storage.get_name_string(name)
        grid = self.grid

        if self._is_displaced:
            if self._xyz_nominal is None:
                self.log_error('the model is displaced, but self._xyz_nominal is None...')
                return
            self._is_displaced = False
            self._update_grid(self._xyz_nominal)

    #def clear_grid_fringe(grid):
        point_data = grid.GetPointData()
        npoint_arrays = point_data.GetNumberOfArrays()
        for i in range(npoint_arrays):
            name = point_data.GetArrayName(i)
            if name is not None:
                #print("pointArray ", i, ": ", name)
                point_data.RemoveArray(name)

        cell_data = grid.GetCellData()
        ncell_arrays = cell_data.GetNumberOfArrays()
        for i in range(ncell_arrays):
            name = cell_data.GetArrayName(i)
            if name is not None:
                #print("cellArray ", i, ": ", name)
                cell_data.RemoveArray(name)

        cell_data.SetActiveScalars(None)
        point_data.SetActiveScalars(None)
        cell_data.SetActiveVectors(None)
        point_data.SetActiveVectors(None)
        self.arrow_actor.SetVisibility(False)
        self.arrow_actor_centroid.SetVisibility(False)

        prop = self.geom_actor.GetProperty()
        prop.SetColor(WHITE)

        # the backface property could be null
        back_prop = vtk.vtkProperty()
        back_prop.SetColor(BLUE)
        self.geom_actor.SetBackfaceProperty(back_prop)
        self.geom_actor.Modified()

        self.hide_legend()
        self.scalar_bar.is_shown = False
        self.vtk_interactor.Render()

        self.res_widget.result_case_window.treeView.fringe.setChecked(False)
        self.res_widget.result_case_window.treeView.disp.setChecked(False)
        self.res_widget.result_case_window.treeView.vector.setChecked(False)

    def _get_fringe_data(self, icase):
        """helper for ``on_fringe``"""
        is_valid = False
        # (grid_result, name_tuple, name_str, data)
        failed_data = (None, None, None, None)

        if not isinstance(icase, integer_types):
            self.log_error('icase=%r is not an integer; type=%s' % (icase, type(icase)))
            return is_valid, failed_data
            #assert isinstance(icase, integer_types), icase

        try:
            case = self.result_cases[icase]
        except KeyError:
            self.log_error('icase=%r is not a valid result_case' % icase)
            return is_valid, failed_data

        label2 = ''
        (obj, (i, name)) = self.result_cases[icase]
        subcase_id = obj.subcase_id
        case = obj.get_result(i, name)

        if case is None:
            # normal result
            self.res_widget.result_case_window.treeView.fringe.setChecked(False)
            #self.res_widget.result_case_window.treeView.disp.setChecked(False)
            #self.res_widget.result_case_window.treeView.vector.setChecked(False)

            #is_legend_shown = False
            self.set_normal_result(icase, name, subcase_id)
            # this is valid, but we want to skip out
            return is_valid, failed_data

        result_type = obj.get_title(i, name)
        data_format = obj.get_data_format(i, name)
        vector_size = obj.get_vector_size(i, name)
        location = obj.get_location(i, name)
        methods = obj.get_methods(i)
        #scale = obj.get_scale(i, name)
        #phase = obj.get_phase(i, name)
        label2 = obj.get_header(i, name)
        out = obj.get_nlabels_labelsize_ncolors_colormap(i, name)
        nlabels, labelsize, ncolors, colormap = out

        normi = self._get_normalized_data(icase)

        #if min_value is None and max_value is None:
            #max_value = normi.max()
            #min_value = normi.min()

        #if min_value is None and max_value is None:
        min_value, max_value = obj.get_min_max(i, name)
        unused_subtitle, label = self.get_subtitle_label(subcase_id)
        if label2:
            label += '; ' + label2

        #================================================
        # flips sign to make colors go from blue -> red
        norm_value = float(max_value - min_value)

        vector_size = 1
        scale = 1.0
        name_tuple = (vector_size, subcase_id, result_type, label, min_value, max_value, scale)
        name_str = self._names_storage.get_name_string(name)
        #return name, normi, vector_size, min_value, max_value, norm_value

        grid_result = self.set_grid_values(name_tuple, normi, vector_size,
                                           min_value, max_value, norm_value)
        data = (
            icase, result_type, location, min_value, max_value, norm_value,
            data_format, scale, methods,
            nlabels, labelsize, ncolors, colormap,
        )
        is_valid = True
        return is_valid, (grid_result, name_tuple, name_str, data)

    def export_case_data(self, icases=None):
        """exports CSVs of the requested cases"""
        if icases is None:
            icases = self.result_cases.keys()
        for icase in icases:
            (obj, (i, name)) = self.result_cases[icase]
            subcase_id = obj.subcase_id
            location = obj.get_location(i, name)

            case = obj.get_result(i, name)
            if case is None:
                continue # normals
            subtitle, label = self.get_subtitle_label(subcase_id)
            label2 = obj.get_header(i, name)
            data_format = obj.get_data_format(i, name)
            vector_size = obj.get_vector_size(i, name)
            print(subtitle, label, label2, location, name)

            word, eids_nids = self.get_mapping_for_location(location)

            # fixing cast int data
            header = '%s(%%i),%s(%s)' % (word, label2, data_format)
            if 'i' in data_format and isinstance(case.dtype, np.floating):
                header = '%s(%%i),%s' % (word, label2)

            fname = '%s_%s.csv' % (icase, name)
            out_data = np.column_stack([eids_nids, case])
            np.savetxt(fname, out_data, delimiter=',', header=header, fmt=b'%s')

    def get_mapping_for_location(self, location):
        """helper method for ``export_case_data``"""
        if location == 'centroid':
            word = 'ElementID'
            eids_nids = self.element_ids
        elif location == 'node':
            word = 'NodeID'
            eids_nids = self.node_ids
        else:
            raise NotImplementedError(location)
        return word, eids_nids

    def _get_normalized_data(self, icase):
        """helper method for ``export_case_data``"""
        (obj, (i, name)) = self.result_cases[icase]
        case = obj.get_result(i, name)
        if case is None:
            return None

        if len(case.shape) == 1:
            normi = case
        else:
            normi = norm(case, axis=1)
        return normi

    def _get_disp_data(self, icase, is_disp):
        """helper for ``on_disp``"""
        is_valid = False
        failed_data = (None, None, None, None)
        #is_checked = self.res_widget.get_checked()
        is_checked = False

        if not isinstance(icase, integer_types):
            self.log_error('icase=%r is not an integer; type=%s' % (icase, type(icase)))
            #self.res_widget.set_checked('normals', is_checked)

            return is_valid, failed_data
            #assert isinstance(icase, integer_types), icase

        try:
            case = self.result_cases[icase]
        except KeyError:
            self.log_error('icase=%r is not a valid result_case' % icase)
            return is_valid, failed_data

        label2 = ''
        (obj, (i, name)) = self.result_cases[icase]
        subcase_id = obj.subcase_id
        case = obj.get_result(i, name)
        if case is None:
            # normal result
            self.log_error('icase=%r is not a displacement/force' % icase)
            return is_valid, failed_data

        result_type = obj.get_title(i, name)
        vector_size = obj.get_vector_size(i, name)
        if vector_size == 1:
            self.log_error('icase=%r is not a displacement/force' % icase)
            return is_valid, failed_data
        location = obj.get_location(i, name)
        if is_disp and location != 'node':
            self.log_error('icase=%r is not a displacement-like (nodal vector) result' % icase)
            return is_valid, failed_data

        xyz_nominal, vector_data = obj.get_vector_result(i, name)
        if is_disp and xyz_nominal is None:
            self.log_error('icase=%r is not a displacement-like (nodal vector) result' % icase)
            return is_valid, failed_data

        methods = obj.get_methods(i)
        data_format = obj.get_data_format(i, name)
        scale = obj.get_scale(i, name)
        phase = obj.get_phase(i, name)
        label2 = obj.get_header(i, name)
        out = obj.get_nlabels_labelsize_ncolors_colormap(i, name)
        nlabels, labelsize, ncolors, colormap = out

        # setup
        #-----
        # make results
        #if len(case.shape) == 1:
            #normi = case
        #else:
            #normi = norm(case, axis=1)

        #if min_value is None and max_value is None:
            #max_value = normi.max()
            #min_value = normi.min()

        #if min_value is None and max_value is None:
        min_value, max_value = obj.get_min_max(i, name)
        unused_subtitle, label = self.get_subtitle_label(subcase_id)
        if label2:
            label += '; ' + label2

        #================================================
        # flips sign to make colors go from blue -> red
        norm_value = float(max_value - min_value)

        vector_size = 3
        name_tuple = (vector_size, subcase_id, result_type, label, min_value, max_value, scale)
        name_str = self._names_storage.get_name_string(name)
        #return name, normi, vector_size, min_value, max_value, norm_value

        #grid_result = self.set_grid_values(name_tuple, normi, vector_size,
                                           #min_value, max_value, norm_value)
        grid_result = None
        min_value = None
        max_value = None
        norm_value = None

        data = (
            icase, result_type, location, min_value, max_value, norm_value,
            data_format, scale, phase, methods,
            nlabels, labelsize, ncolors, colormap,
            xyz_nominal, vector_data,
            is_checked,
        )
        is_valid = True
        return is_valid, (grid_result, name_tuple, name_str, data)

    def on_fringe(self, icase, show_msg=True):
        """
        Sets the icase data to the active fringe

        Parameters
        ----------
        case : int; default=None
            selects the icase
            None : defaults to self.icase+1
        """
        self.icase = icase
        is_valid, (grid_result, name, name_str, data) = self._get_fringe_data(icase)

        if not is_valid:
            return
        (
            icase, result_type, location, min_value, max_value, norm_value,
            data_format, scale, methods,
            nlabels, labelsize, ncolors, colormap,
        ) = data

        #(obj, (obj_i, obj_name)) = self.result_cases[self.icase]
        #obj_location = obj.get_location(obj_i, obj_name)
        #obj_location = ''
        #-----------------------------------
        grid = self.grid
        phase = 0.0

        grid_result.SetName(name_str)
        self._names_storage.add(name)

        cell_data = grid.GetCellData()
        point_data = grid.GetPointData()
        if location == 'centroid':
            #cell_data.RemoveArray(name_str)
            self._names_storage.remove(name)
            cell_data.AddArray(grid_result)

            #if location != obj_location:
            point_data.SetActiveScalars(None)
            cell_data.SetActiveScalars(name_str)

        elif location == 'node':
            #point_data.RemoveArray(name_str)
            self._names_storage.remove(name)
            point_data.AddArray(grid_result)

            #if location != obj_location:
            cell_data.SetActiveScalars(None)
            point_data.SetActiveScalars(name_str)
        else:
            raise RuntimeError(location)

        is_low_to_high = True
        #self._legend_window_shown = False
        #self.update_legend(
            #icase,
            #result_type, min_value, max_value, data_format, scale, phase,
            #nlabels, labelsize, ncolors, colormap,
            #is_low_to_high, self.is_horizontal_scalar_bar)
        #self.on_update_legend(title=title, min_value=min_value, max_value=max_value,
                              #scale=scale, phase=phase, data_format=data_format,
                              #is_low_to_high=is_low_to_high,
                              ##is_discrete=is_discrete,
                              ##is_horizontal=is_horizontal,
                              #nlabels=nlabels, labelsize=labelsize,
                              #ncolors=ncolors, colormap=colormap,
                              #is_shown=True)

        #is_legend_shown = True
        #if is_legend_shown is None:
        is_legend_shown = self.scalar_bar.is_shown

        # TODO: normal -> fringe screws up legend
        #print('is_legend_shown = ', is_legend_shown)
        if not is_legend_shown:
            #print('shownig')
            self.show_legend()

        self.update_scalar_bar(result_type, min_value, max_value, norm_value,
                               data_format,
                               nlabels=nlabels, labelsize=labelsize,
                               ncolors=ncolors, colormap=colormap,
                               is_low_to_high=is_low_to_high,
                               is_horizontal=self.is_horizontal_scalar_bar,
                               is_shown=is_legend_shown)

        self.update_legend(icase,
                           result_type, min_value, max_value, data_format, scale, phase,
                           nlabels, labelsize, ncolors, colormap,
                           is_low_to_high, self.is_horizontal_scalar_bar)
        self.res_widget.update_method(methods)

        self.grid.Modified()
        self.grid_selected.Modified()
        self.vtk_interactor.Render()
        self.res_widget.result_case_window.treeView.fringe.setChecked(True)

    def on_disp(self, icase, apply_fringe=False, show_msg=True):
        is_disp = True
        self._on_disp_vector(icase, is_disp, apply_fringe, show_msg=show_msg)
        self.res_widget.result_case_window.treeView.disp.setChecked(True)

    def on_vector(self, icase, apply_fringe=False, show_msg=True):
        is_disp = False
        self._on_disp_vector(icase, is_disp, apply_fringe, show_msg=show_msg)
        self.res_widget.result_case_window.treeView.vector.setChecked(True)

    def _on_disp_vector(self, icase, is_disp, apply_fringe=False, show_msg=True):
        """
        Sets the icase data to the active displacement

        Parameters
        ----------
        case : int; default=None
            selects the icase
            None : defaults to self.icase+1
        """
        self.icase = icase
        is_valid, (grid_result, name, name_str, data) = self._get_disp_data(icase, is_disp)

        if not is_valid:
            return
        (
            icase, unused_result_type, location, unused_min_value, unused_max_value, unused_norm_value,
            unused_data_format, scale, unused_phase, unused_methods,
            unused_nlabels, unused_labelsize, unused_ncolors, unused_colormap,
            xyz_nominal, vector_data,
            unused_is_checked,
        ) = data
        #deflects = obj.deflects(i, res_name)

        #(obj, (obj_i, obj_name)) = self.result_cases[self.icase]
        #obj_location = obj.get_location(obj_i, obj_name)
        #obj_location = ''
        #-----------------------------------
        grid = self.grid
        #phase = 0.0

        if 0:
            grid_result.SetName(name_str)
            self._names_storage.add(name)

            self.log_debug('icase=%s location=%s' % (icase, location))
            cell_data = grid.GetCellData()
            point_data = grid.GetPointData()

            if location == 'centroid':
                #cell_data.RemoveArray(name_str)
                self._names_storage.remove(name)
                cell_data.AddArray(grid_result)

                #if location != obj_location:
                point_data.SetActiveVectors(None)
                cell_data.SetActiveVectors(name_str)

            elif location == 'node':
                #point_data.RemoveArray(name_str)
                self._names_storage.remove(name)
                point_data.AddArray(grid_result)

                #if location != obj_location:
                cell_data.SetActiveVectors(None)
                point_data.SetActiveVectors(name_str)
            else:
                raise RuntimeError(location)

        print('disp=%s location=%r' % (is_disp, location))
        if is_disp: # or obj.deflects(i, res_name):
            #grid_result1 = self.set_grid_values(name, case, 1,
                                                #min_value, max_value, norm_value)
            #point_data.AddArray(grid_result1)

            self._is_displaced = True
            self._is_forces = False
            self._xyz_nominal = xyz_nominal
            self._update_grid(vector_data)

            self.grid.Modified()
            self.grid_selected.Modified()
        else:
            if location == 'node':
                #self._is_displaced = False
                self._is_forces = True
                #xyz_nominal, vector_data = obj.get_vector_result(i, res_name)
                self._update_forces(vector_data, set_scalars=apply_fringe, scale=scale)
            else:
                #self._is_displaced = False
                self._is_forces = True
                #xyz_nominal, vector_data = obj.get_vector_result(i, res_name)
                self._update_elemental_vectors(vector_data, set_scalars=apply_fringe, scale=scale)

        #is_low_to_high = True
        #self.log_info('min_value=%s, max_value=%s' % (min_value, max_value))

        #is_legend_shown = True
        #if is_legend_shown is None:
        #is_legend_shown = self.scalar_bar.is_shown
        #self.log_debug('is_legend_shown = %s' % is_legend_shown)

        #self.update_legend(icase,
                           #result_type, min_value, max_value, data_format, scale, phase,
                           #nlabels, labelsize, ncolors, colormap,
                           #is_low_to_high, self.is_horizontal_scalar_bar)
        #self.res_widget.update_method(methods)

        self.vtk_interactor.Render()


    def cycle_results_explicit(self, case=None, explicit=True, min_value=None, max_value=None,
                               show_msg=True):
        assert case is not False, case
        #if explicit:
            #self.log_command('cycle_results(case=%r)' % case)
        found_cases = self.increment_cycle(case)
        if found_cases:
            icase = self._set_case(case, self.icase, explicit=explicit, cycle=True,
                                   min_value=min_value, max_value=max_value, show_msg=show_msg)
            assert icase is not False, case
        else:
            icase = None
        return icase

    def get_name_result_data(self, icase):
        key = self.case_keys[icase]
        assert isinstance(key, integer_types), key
        (obj, (i, name)) = self.result_cases[key]
        #subcase_id = obj.subcase_id
        case = obj.get_result(i, name)
        return name, case

    def delete_cases(self, icases_to_delete, ask=True):
        """
        Used by the Sidebar to delete results

        Parameters
        ----------
        icases_to_delete : List[int]
            the result cases to delete
        ask : bool; default=True
            TODO: does nothing...
        """
        for icase in icases_to_delete:
            if icase not in self.case_keys:
                continue
            self.case_keys.remove(icase)
            del self.result_cases[icase]

            # we leave this, so we can still cycle the results without renumbering the cases
            #self.ncases -= 1
        self.log_command('delete_cases(icases_to_delete=%s, ask=%s)' % (icases_to_delete, ask))

    def _get_sidebar_data(self, unused_name):
        """
        gets the form for the selected name

        Parameters
        ----------
        name : str
            the name that was selected

        Returns
        -------
        form : List[tuple]
            the form data
        """
        return []

    def _set_case(self, unused_result_name, icase, explicit=False, cycle=False,
                  skip_click_check=False, min_value=None, max_value=None,
                  is_legend_shown=None, show_msg=True):
        """
        Internal method for doing results updating

        unused_result_name : str
            the name of the case for debugging purposes
        icase : int
            the case id
        cycle : bool; default=False
            ???
        skip_click_check : bool; default=False
            There is no reason to update if the case didn't change on the
            Results Sidebar
            True  : Legend Menu
            False : Results Sidebar
        min_value : float; default=None
            the min value
            None : use the default
        max_value  : float; default=None
            the max value
            None : use the default
        is_legend_shown : bool; default=None
            is the scalar bar shown
            None : stick with the current value
            True : show the legend
            False : hide the legend
        explicit : bool; default=False
            show the command when we're doing in the log
        show_msg : bool; default=True
            ???
        """
        if not skip_click_check:
            if not cycle and icase == self.icase:
                # don't click the button twice
                # cycle=True means we're cycling
                # cycle=False skips that check
                return

        try:
            key = self.case_keys[icase]
        except KeyError:
            print('icase=%s case_keys=%s' % (icase, str(self.case_keys)))
            raise
        self.icase = icase
        case = self.result_cases[key]
        label2 = ''
        assert isinstance(key, integer_types), key
        (obj, (i, name)) = self.result_cases[key]
        subcase_id = obj.subcase_id
        case = obj.get_result(i, name)
        result_type = obj.get_title(i, name)
        vector_size = obj.get_vector_size(i, name)
        #location = obj.get_location(i, name)
        methods = obj.get_methods(i)
        data_format = obj.get_data_format(i, name)
        scale = obj.get_scale(i, name)
        phase = obj.get_phase(i, name)
        label2 = obj.get_header(i, name)
        out = obj.get_nlabels_labelsize_ncolors_colormap(i, name)
        nlabels, labelsize, ncolors, colormap = out
        #default_max, default_min = obj.get_default_min_max(i, name)
        if min_value is None and max_value is None:
            min_value, max_value = obj.get_min_max(i, name)

        #if 0:
            # my poor attempts at supporting NaN colors
            #if min_value is None and max_value is None:
                #max_value = case.max()
                #min_value = case.min()
            #if np.isnan(max_value):
                #inotnan = not np.isnan(case)
                #max_value = case[inotnan].max()
                #min_value = case[inotnan].min()
                #print('max_value = ', max_value)

        subtitle, label = self.get_subtitle_label(subcase_id)
        if label2:
            label += '; ' + label2
        #print("subcase_id=%s result_type=%r subtitle=%r label=%r"
              #% (subcase_id, result_type, subtitle, label))

        #================================================
        is_low_to_high = True
        if case is None:
            return self.set_normal_result(icase, name, subcase_id)

        elif self._is_normals and self.legend_shown:
            # we hacked the scalar bar to turn off for Normals
            # so we turn it back on if we need to
            self._is_normals = False
            self.show_legend()

        if len(case.shape) == 1:
            normi = case
        else:
            normi = norm(case, axis=1)

        #if min_value is None and max_value is None:
            #max_value = normi.max()
            #min_value = normi.min()

        #================================================
        # flips sign to make colors go from blue -> red
        norm_value = float(max_value - min_value)

        vector_size = 1
        name = (vector_size, subcase_id, result_type, label, min_value, max_value, scale)
        if self._names_storage.has_exact_name(name):
            grid_result = None
        else:
            grid_result = self.set_grid_values(name, normi, vector_size,
                                               min_value, max_value, norm_value)

        vector_size = 3
        name_vector = (vector_size, subcase_id, result_type, label, min_value, max_value, scale)
        if self._names_storage.has_exact_name(name_vector):
            grid_result_vector = None
        else:
            grid_result_vector = self.set_grid_values(name_vector, case, vector_size,
                                                      min_value, max_value, norm_value)

        self.update_text_actors(subcase_id, subtitle,
                                min_value, max_value, label)

        self.final_grid_update(name, grid_result,
                               name_vector, grid_result_vector,
                               key, subtitle, label, show_msg)

        if is_legend_shown is None:
            is_legend_shown = self.scalar_bar.is_shown
        self.update_scalar_bar(result_type, min_value, max_value, norm_value,
                               data_format,
                               nlabels=nlabels, labelsize=labelsize,
                               ncolors=ncolors, colormap=colormap,
                               is_low_to_high=is_low_to_high,
                               is_horizontal=self.is_horizontal_scalar_bar,
                               is_shown=is_legend_shown)

        self.update_legend(icase,
                           result_type, min_value, max_value, data_format, scale, phase,
                           nlabels, labelsize, ncolors, colormap,
                           is_low_to_high, self.is_horizontal_scalar_bar)

        # updates the type of the result that is displayed
        # method:
        #     for a nodeID, the method is [node]
        #     for an elementID, the method is [centroid]
        #     for a displacement, the methods are [magnitude, tx, ty, tz, rx, ry, rz]
        # location:
        #     for a nodeID, the location is [node]
        #     for an elementID, the location is [centroid]
        #     for a displacement, the location is [node]

        #location = self.get_case_location(key)
        self.res_widget.update_method(methods)
        if explicit:
            self.log_command('cycle_results(case=%r)' % self.icase)
        assert self.icase is not False, self.icase
        return self.icase

    def set_normal_result(self, icase, name, subcase_id):
        """plots a NormalResult"""
        unused_name_str = self._names_storage.get_name_string(name)
        prop = self.geom_actor.GetProperty()

        prop.SetColor(RED)

        # the backface property is null
        #back_prop = self.geom_actor.GetBackfaceProperty()
        back_prop = vtk.vtkProperty()
        back_prop.SetColor(BLUE)
        self.geom_actor.SetBackfaceProperty(back_prop)

        grid = self.grid
        if self._is_displaced:
            self._is_displaced = False
            self._update_grid(self._xyz_nominal)

        if self._is_forces:
            self.arrow_actor.SetVisibility(False)

        cell_data = grid.GetCellData()
        cell_data.SetActiveScalars(None)

        point_data = grid.GetPointData()
        point_data.SetActiveScalars(None)

        #if is_legend_shown is None:
            #is_legend_shown = self.scalar_bar.is_shown
        #self.update_scalar_bar(result_type, min_value, max_value, norm_value,
                               #data_format,
                               #nlabels=nlabels, labelsize=labelsize,
                               #ncolors=ncolors, colormap=colormap,
                               #is_low_to_high=is_low_to_high,
                               #is_horizontal=self.is_horizontal_scalar_bar,
                               #is_shown=is_legend_shown)
        #scale = 0.0
        #phase = None

        #min_value = -1.
        #max_value = 1.
        #self.update_legend(icase,
                           #result_type, min_value, max_value, data_format, scale, phase,
                           #nlabels, labelsize, ncolors, colormap,
                           #is_low_to_high, self.is_horizontal_scalar_bar)
        self.hide_legend()
        self._is_normals = True
        #min_value = 'Front Face'
        #max_value = 'Back Face'
        #self.update_text_actors(subcase_id, subtitle,
                                #min_value, max_value, label)
        self.vtk_interactor.Render()


    def set_grid_values(self, name, case, vector_size, min_value, max_value, norm_value,
                        is_low_to_high=True):
        """
        https://pyscience.wordpress.com/2014/09/06/numpy-to-vtk-converting-your-numpy-arrays-to-vtk-arrays-and-files/
        """
        if self._names_storage.has_exact_name(name):
            return
        #print('name=%r case=%r' % (name, case))

        if not hasattr(case, 'dtype'):
            raise RuntimeError('name=%s case=%s' % (name, case))

        if issubdtype(case.dtype, np.integer):
            data_type = vtk.VTK_INT
            self.grid_mapper.InterpolateScalarsBeforeMappingOn()
        elif issubdtype(case.dtype, np.floating):
            data_type = vtk.VTK_FLOAT
            self.grid_mapper.InterpolateScalarsBeforeMappingOff()
        else:
            raise NotImplementedError(case.dtype.type)


        #if 0: # nan testing
            #if case.dtype.name == 'float32':
                #case[50] = np.float32(1) / np.float32(0)
            #else:
                #case[50] = np.int32(1) / np.int32(0)

        if vector_size == 1:
            nvalues = len(case)
            if is_low_to_high:
                if norm_value == 0:
                    case2 = full((nvalues), 1.0 - min_value, dtype='float32')
                else:
                    case2 = 1.0 - (case - min_value) / norm_value
            else:
                if norm_value == 0:
                    case2 = full((nvalues), min_value, dtype='float32')
                else:
                    case2 = (case - min_value) / norm_value

            if case.flags.contiguous:
                case2 = case
            else:
                case2 = deepcopy(case)
            grid_result = numpy_to_vtk(
                num_array=case2,
                deep=True,
                array_type=data_type
            )
            #print('grid_result = %s' % grid_result)
            #print('max2 =', grid_result.GetRange())
        else:
            # vector_size=3
            if case.flags.contiguous:
                case2 = case
            else:
                case2 = deepcopy(case)
            grid_result = numpy_to_vtk(
                num_array=case2,
                deep=True,
                array_type=data_type
            )
        return grid_result

    def update_grid_by_icase_scale_phase(self, icase, scale, phase=0.0):
        """
        Updates to the deflection state defined by the cases

        Parameters
        ----------
        icase : int
            result number in self.result_cases
        scale : float
            deflection scale factor; true scale
        phase : float; default=0.0
            phase angle (degrees); unused for real results

        Returns
        -------
        xyz : (nnodes, 3) float ndarray
            the nominal state
        deflected_xyz : (nnodes, 3) float ndarray
            the deflected state
        """
        #print('update_grid_by_icase_scale_phase')
        (obj, (i, res_name)) = self.result_cases[icase]
        xyz_nominal, vector_data = obj.get_vector_result_by_scale_phase(
            i, res_name, scale, phase)

        #grid_result1 = self.set_grid_values(name, case, 1,
            #min_value, max_value, norm_value)
        #point_data.AddArray(grid_result1)

        self._is_displaced = True
        self._xyz_nominal = xyz_nominal
        self._update_grid(vector_data)

    def final_grid_update(self, name, grid_result,
                          name_vector, grid_result_vector,
                          key, subtitle, label, show_msg):
        assert isinstance(key, integer_types), key
        (obj, (i, res_name)) = self.result_cases[key]
        subcase_id = obj.subcase_id
        result_type = obj.get_title(i, res_name)
        vector_size = obj.get_vector_size(i, res_name)
        location = obj.get_location(i, res_name)

        #if vector_size == 3:
            #print('name, grid_result, vector_size=3', name, grid_result)
        self._final_grid_update(name, grid_result, None, None, None,
                                1, subcase_id, result_type, location, subtitle, label,
                                revert_displaced=True, show_msg=show_msg)
        if vector_size == 3:
            self._final_grid_update(name_vector, grid_result_vector, obj, i, res_name,
                                    vector_size, subcase_id, result_type, location, subtitle, label,
                                    revert_displaced=False, show_msg=show_msg)
            #xyz_nominal, vector_data = obj.get_vector_result(i, res_name)
            #self._update_grid(vector_data)

    def _final_grid_update(self, name, grid_result, obj, i, res_name,
                           vector_size, subcase_id, result_type, location, subtitle, label,
                           revert_displaced=True, show_msg=True):
        if name is None:
            return

        # the result type being currently shown
        # for a Nastran NodeID/displacement, this is 'node'
        # for a Nastran ElementID/PropertyID, this is 'element'
        self.result_location = location

        grid = self.grid
        name_str = self._names_storage.get_name_string(name)
        if not self._names_storage.has_exact_name(name):
            grid_result.SetName(name_str)
            self._names_storage.add(name)

            if self._is_displaced and revert_displaced:
                self._is_displaced = False
                self._update_grid(self._xyz_nominal)

            if self._is_forces:
                self.arrow_actor.SetVisibility(False)

            if location == 'centroid':
                cell_data = grid.GetCellData()
                if self._names_storage.has_close_name(name):
                    cell_data.RemoveArray(name_str)
                    self._names_storage.remove(name)

                cell_data.AddArray(grid_result)
                if show_msg:
                    self.log_info('centroidal plotting vector=%s - subcase_id=%s '
                                  'result_type=%s subtitle=%s label=%s'
                                  % (vector_size, subcase_id, result_type, subtitle, label))
            elif location == 'node':
                point_data = grid.GetPointData()
                if self._names_storage.has_close_name(name):
                    point_data.RemoveArray(name_str)
                    self._names_storage.remove(name)

                if vector_size == 1:
                    if show_msg:
                        self.log_info('node plotting vector=%s - subcase_id=%s '
                                      'result_type=%s subtitle=%s label=%s"'
                                      % (vector_size, subcase_id, result_type, subtitle, label))
                    point_data.AddArray(grid_result)
                elif vector_size == 3:
                    #print('vector_size3; get, update')

                    xyz_nominal, vector_data = obj.get_vector_result(i, res_name)
                    if obj.deflects(i, res_name):
                        #grid_result1 = self.set_grid_values(name, case, 1,
                                                            #min_value, max_value, norm_value)
                        #point_data.AddArray(grid_result1)

                        self._is_displaced = True
                        self._is_forces = False
                        self._xyz_nominal = xyz_nominal
                        self._update_grid(vector_data)
                    else:
                        self._is_displaced = False
                        self._is_forces = True
                        scale = obj.get_scale(i, res_name)
                        xyz_nominal, vector_data = obj.get_vector_result(i, res_name)
                        self._update_forces(vector_data, scale)

                    if show_msg:
                        self.log_info('node plotting vector=%s - subcase_id=%s '
                                      'result_type=%s subtitle=%s label=%s'
                                      % (vector_size, subcase_id, result_type, subtitle, label))
                    #point_data.AddVector(grid_result) # old
                    #point_data.AddArray(grid_result)
                else:
                    raise RuntimeError(vector_size)
            else:
                raise RuntimeError(location)

        if location == 'centroid':
            cell_data = grid.GetCellData()
            cell_data.SetActiveScalars(name_str)

            point_data = grid.GetPointData()
            point_data.SetActiveScalars(None)
            if vector_size == 1:
                #point_data.SetActiveVectors(None)   # I don't think I need this
                pass
            else:
                raise RuntimeError(vector_size)
        elif location == 'node':
            cell_data = grid.GetCellData()
            cell_data.SetActiveScalars(None)

            point_data = grid.GetPointData()
            if vector_size == 1:
                point_data.SetActiveScalars(name_str)  # TODO: None???
            elif vector_size == 3:
                pass
                #point_data.SetActiveVectors(name_str)
            else:
                raise RuntimeError(vector_size)
            #print('name_str=%r' % name_str)
        else:
            raise RuntimeError(location)

        grid.Modified()
        self.grid_selected.Modified()
        #self.update_all()
        #self.update_all()
        if len(self.groups):
            self.post_group_by_name(self.group_active)
        self.vtk_interactor.Render()

        self.hide_labels(show_msg=False)
        self.show_labels(case_keys=[self.icase], show_msg=False)

    def _update_forces(self, forces_array, set_scalars=True, scale=None):
        """changes the glyphs"""
        grid = self.grid
        if scale is not None:
            self.glyphs.SetScaleFactor(self.glyph_scale_factor * scale)
        mag = np.linalg.norm(forces_array, axis=1)
        #assert len(forces_array) == len(mag)

        mag_max = mag.max()
        new_forces = np.copy(forces_array / mag_max)
        #mag /= mag_max

        #inonzero = np.where(mag > 0)[0]
        #print('new_forces_max =', new_forces.max())
        #print('new_forces =', new_forces[inonzero])
        #print('mag =', mag[inonzero])

        vtk_vectors = numpy_to_vtk(new_forces, deep=1)

        grid.GetPointData().SetVectors(vtk_vectors)
        if set_scalars:
            vtk_mag = numpy_to_vtk(mag, deep=1)
            grid.GetPointData().SetScalars(vtk_mag)
            grid.GetCellData().SetScalars(None)
        self.arrow_actor.SetVisibility(True)
        grid.Modified()
        self.grid_selected.Modified()

    def _update_elemental_vectors(self, forces_array, set_scalars=True, scale=None):
        """changes the glyphs"""
        grid = self.grid
        if scale is not None:
            # TODO: glyhs_centroid?
            self.glyphs_centroid.SetScaleFactor(self.glyph_scale_factor * scale)
        mag = np.linalg.norm(forces_array, axis=1)
        #assert len(forces_array) == len(mag)

        mag_max = mag.max()
        new_forces = np.copy(forces_array / mag_max)
        #mag /= mag_max

        #inonzero = np.where(mag > 0)[0]
        #print('new_forces_max =', new_forces.max())
        #print('new_forces =', new_forces[inonzero])
        #print('mag =', mag[inonzero])

        vtk_vectors = numpy_to_vtk(new_forces, deep=1)

        grid.GetPointData().SetVectors(None)
        #print('_update_elemental_vectors; shape=%s' % (str(new_forces.shape)))
        grid.GetCellData().SetVectors(vtk_vectors)
        if set_scalars:
            vtk_mag = numpy_to_vtk(mag, deep=1)
            grid.GetPointData().SetScalars(None)
            grid.GetCellData().SetScalars(vtk_mag)
        self.arrow_actor_centroid.SetVisibility(True)
        grid.Modified()
        self.grid_selected.Modified()

    def _update_grid(self, nodes):
        """deflects the geometry"""
        grid = self.grid
        points = grid.GetPoints()
        #inan = np.where(nodes.ravel() == np.nan)[0]
        #if len(inan) > 0:
            #raise RuntimeError('nan in nodes...')
        numpy_to_vtk_points(nodes, points=points, dtype='<f', deep=1)
        grid.Modified()
        self.grid_selected.Modified()
        self._update_follower_grids(nodes)
        self._update_follower_grids_complex(nodes)

    def _update_follower_grids(self, nodes):
        """updates grids that use the same ids as the parent model"""
        for name, nids in iteritems(self.follower_nodes):
            grid = self.alt_grids[name]
            points = grid.GetPoints()
            for j, nid in enumerate(nids):
                i = self.nid_map[nid]
                points.SetPoint(j, *nodes[i, :])
            grid.Modified()

    def _update_follower_grids_complex(self, nodes):
        """updates grids that use a complicated update method"""
        for name, follower_function in iteritems(self.follower_functions):
            grid = self.alt_grids[name]
            points = grid.GetPoints()
            follower_function(self.nid_map, grid, points, nodes)
            grid.Modified()

    def _get_icase(self, result_name):
        if not self.result_cases:
            raise IndexError('result_name=%r not in self.result_cases' % result_name)

        #print('result_cases.keys() =', self.result_cases.keys())
        i = 0
        for icase in sorted(iterkeys(self.result_cases)):
            #cases = self.result_cases[icase]
            if result_name == icase[1]:
                unused_found_case = True
                icase = i
                break
            i += 1
        return icase

    def increment_cycle(self, icase=None):
        #print('1-icase=%r self.icase=%s ncases=%r' % (icase, self.icase, self.ncases))
        #print(type(icase))
        if isinstance(icase, integer_types):
            self.icase = icase
            if self.icase >= self.ncases:
                self.icase = 0
        else:
            self.icase += 1
            if self.icase == self.ncases:
                self.icase = 0
        #print('2-icase=%r self.icase=%s ncases=%r' % (icase, self.icase, self.ncases))

        if self.ncases > 0:
            #key = self.case_keys[self.icase]
            #try:
                #key = self.case_keys[self.icase]
            #except IndexError:
                #found_cases = False
                #return found_cases
            #except TypeError:
                #msg = 'type(case_keys)=%s\n' % type(self.case_keys)
                #msg += 'icase=%r\n' % str(self.icase)
                #msg += 'case_keys=%r' % str(self.case_keys)
                #print(msg)
                #raise TypeError(msg)
            msg = 'icase=%r\n' % str(self.icase)
            msg += 'case_keys=%r' % str(self.case_keys)
            #print(msg)
            found_cases = True
        else:
            # key = self.case_keys[self.icase]
            # location = self.get_case_location(key)
            self.log_error('No results found.')
            self.scalarBar.SetVisibility(False)
            found_cases = False
        #print("next icase=%s key=%s" % (self.icase, key))
        return found_cases

    def get_result_name(self, key):
        assert isinstance(key, integer_types), key
        (unused_obj, (unused_i, name)) = self.result_cases[key]
        return name

    def get_case_location(self, key):
        assert isinstance(key, integer_types), key
        (obj, (i, name)) = self.result_cases[key]
        return obj.get_location(i, name)
