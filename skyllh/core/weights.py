# -*- coding: utf-8 -*-

"""This module contains utility classes related to calculate weights.
"""

from collections import defaultdict
import numpy as np

from skyllh.core.detsigyield import (
    DetSigYield,
)
from skyllh.core.py import (
    issequence,
    issequenceof,
)
from skyllh.core.source_hypo_grouping import (
    SourceHypoGroupManager,
)


class SrcDetSigYieldWeightsService(object):
    r"""This class provides a service for the source detector signal yield
    weights, which are the product of the source weights with the detector
    signal yield, denoted with :math:`a_{j,k}(\vec{p}_{\mathrm{s}_k})` in the
    math formalism documentation.

    .. math::

        a_{j,k}(\vec{p}_{\mathrm{s}_k}) = W_k
            \mathcal{Y}_{\mathrm{s}_{j,k}}(\vec{p}_{\mathrm{s}_k})

    The service has a method to calculate the weights and a method to retrieve
    the weights. The weights are stored internally.
    """

    @staticmethod
    def create_src_recarray_list_list(shg_mgr, detsigyield_arr):
        """Creates a list of numpy record ndarrays, one for each source
        hypothesis group suited for evaluating the detector signal yield
        instance of that source hypothesis group.

        Parameters
        ----------
        shg_mgr : instance of SourceHypoGroupManager
            The instance of SourceHypoGroupManager defining the source
            hypothesis groups with their sources.
        detsigyield_arr : instance of ndarray of instance of DetSigYield
            The (N_datasets,N_source_hypo_groups)-shaped 1D ndarray of
            DetSigYield instances, one for each dataset and source hypothesis
            group combination.

        Returns
        -------
        src_recarray_list_list : list of list of numpy record ndarrays
            The (N_datasets,N_source_hypo_groups)-shaped list of list of the
            source numpy record ndarrays, one for each dataset and source
            hypothesis group combination, which is needed for
            evaluating a particular detector signal yield instance.
        """
        n_datasets = detsigyield_arr.shape[0]
        n_shgs = detsigyield_arr.shape[1]
        shg_list = shg_mgr.shg_list

        src_recarray_list_list = []
        for ds_idx in range(n_datasets):
            src_recarray_list = []
            for shg_idx in range(n_shgs):
                shg = shg_list[shg_idx]
                src_recarray_list.append(
                    detsigyield_arr[ds_idx][shg_idx].sources_to_recarray(
                        shg.source_list))

            src_recarray_list_list.append(src_recarray_list)

        return src_recarray_list_list

    @staticmethod
    def create_src_weight_array_list(shg_mgr):
        """Creates a list of numpy 1D ndarrays holding the source weights, one
        for each source hypothesis group.

        Parameters
        ----------
        shg_mgr : instance of SourceHypoGroupManager
            The instance of SourceHypoGroupManager defining the source
            hypothesis groups with their sources.

        Returns
        -------
        src_weight_array_list : list of numpy 1D ndarrays
            The list of 1D numpy ndarrays holding the source weights, one for
            each source hypothesis group.
        """
        src_weight_array_list = [
            np.array([src.weight for src in shg.source_list])
            for shg in shg_mgr.shg_list
        ]
        return src_weight_array_list

    def __init__(
            self,
            shg_mgr,
            detsigyields):
        """Creates a new SrcDetSigYieldWeightsService instance.

        Parameters
        ----------
        shg_mgr : instance of SourceHypoGroupManager
            The instance of SourceHypoGroupManager defining the sources and
            their source hypothesis groups.
        detsigyields : sequence of sequence of instance of DetSigYield
            The (N_datasets,N_source_hypo_groups)-shaped sequence of sequence of
            DetSigYield instances, one instance for each combination of dataset
            and source hypothesis group.
        """
        self._set_shg_mgr(
            shg_mgr=shg_mgr)

        if not issequence(detsigyields):
            detsigyields = [detsigyields]
        for item in detsigyields:
            if not issequenceof(item, DetSigYield):
                raise TypeError(
                    'The detsigyields argument must be a sequence of sequence '
                    'of DetSigYield instances!')
        self._detsigyield_arr = np.atleast_2d(detsigyields)
        if self._detsigyield_arr.shape[1] != self._shg_mgr.n_src_hypo_groups:
            raise ValueError(
                'The length of the second dimension of the detsigyields array '
                'must be equal to the number of source hypothesis groups which '
                'the source hypothesis group manager defines!')

        # Create the list of list of source record arrays for each combination
        # of dataset and source hypothesis group.
        self._src_recarray_list_list = type(self).create_src_recarray_list_list(
            shg_mgr=self._shg_mgr,
            detsigyield_arr=self._detsigyield_arr)

        # Create the list of 1D ndarrays holding the source weights for each
        # source hypothesis group.
        self._src_weight_array_list = type(self).create_src_weight_array_list(
            shg_mgr=self._shg_mgr)

        self._a_jk = None
        self._a_jk_grads = None

    @property
    def shg_mgr(self):
        """(read-only) The instance of SourceHypoGroupManager defining the
        source hypothesis groups.
        """
        return self._shg_mgr

    @property
    def detsigyield_arr(self):
        """(read-only) The (N_datasets,N_source_hypo_groups)-shaped 1D numpy
        ndarray holding the DetSigYield instances for each source hypothesis
        group.
        """
        return self._detsigyield_arr

    @property
    def n_datasets(self):
        """(read-only) The number of datasets this service is created with.
        """
        return self._detsigyield_arr.shape[0]

    @property
    def src_recarray_list_list(self):
        """(read-only) The (N_datasets,N_source_hypo_groups)-shaped list of list
        of the source numpy record ndarrays, one for each dataset and source
        hypothesis group combination, which is needed for evaluating a
        particular detector signal yield instance.
        """
        return self._src_recarray_list_list

    def _set_shg_mgr(self, shg_mgr):
        """Sets the _shg_mgr class attribute and checks for the correct type.

        Parameters
        ----------
        shg_mgr : instance of SourceHypoGroupManager
            The instance of SourceHypoGroupManager that should be set.
        """
        if not isinstance(shg_mgr, SourceHypoGroupManager):
            raise TypeError(
                'The shg_mgr argument must be an instance of '
                'SourceHypoGroupManager!')
        self._shg_mgr = shg_mgr

    def change_shg_mgr(self, shg_mgr):
        """Changes the SourceHypoGroupManager instance of this
        SourceDetectorWeights instance. This will also re-create the internal
        source numpy record arrays needed for the detector signal yield
        calculation.

        Parameters
        ----------
        shg_mgr : instance of SourceHypoGroupManager
            The new SourceHypoGroupManager instance.
        """
        self._set_shg_mgr(
            shg_mgr=shg_mgr)
        self._src_recarray_list_list = type(self).create_src_recarray_list_list(
            shg_mgr=self._shg_mgr,
            detsigyield_arr=self._detsigyield_arr)
        self._src_weight_array_list = type(self).create_src_weight_array_list(
            shg_mgr=self._shg_mgr)

    def calculate(self, src_params_recarray):
        """Calculates the source detector signal yield weights for each source
        and their derivative w.r.t. each global floating parameter. The result
        is stored internally as:

            a_jk : instance of ndarray
                The (N_datasets,N_sources)-shaped numpy ndarray holding the
                source detector signal yield weight for each combination of
                dataset and source.
            a_jk_grads : dict
                The dictionary holding the (N_datasets,N_sources)-shaped numpy
                ndarray with the derivatives w.r.t. the global fit parameter
                the SrcDetSigYieldWeightsService depend on. The dictionary's key
                is the index of the global fit parameter.

        Parameters
        ----------
        src_params_recarray : instance of numpy record ndarray
            The numpy record ndarray of length N_sources holding the local
            source parameters. See the documentation of
            :meth:`skyllh.core.parameters.ParameterModelMapper.create_src_params_recarray`
            for more information about this record array.
        """
        n_datasets = self.n_datasets

        self._a_jk = np.empty(
            (n_datasets, self.shg_mgr.n_sources,),
            dtype=np.double)

        self._a_jk_grads = defaultdict(
            lambda: np.zeros(
                (n_datasets, self.shg_mgr.n_sources),
                dtype=np.double))

        sidx = 0
        for (shg_idx, (shg, src_weights)) in enumerate(zip(
                self.shg_mgr.shg_list, self._src_weight_array_list)):

            shg_n_src = shg.n_sources

            shg_src_slice = slice(sidx, sidx+shg_n_src)

            shg_src_params_recarray = src_params_recarray[shg_src_slice]

            for ds_idx in range(n_datasets):
                detsigyield = self._detsigyield_arr[ds_idx, shg_idx]
                src_recarray = self._src_recarray_list_list[ds_idx][shg_idx]

                (Yg, Yg_grads) = detsigyield(
                    src_recarray=src_recarray,
                    src_params_recarray=shg_src_params_recarray)

                self._a_jk[ds_idx][shg_src_slice] = src_weights * Yg

                for gpidx in Yg_grads.keys():
                    self._a_jk_grads[gpidx][ds_idx, shg_src_slice] =\
                        src_weights * Yg_grads[gpidx]

            sidx += shg_n_src

    def get_weights(self):
        """Returns the source detector signal yield weights and their
        derivatives w.r.t. the global fit parameters.

        Returns
        -------
        a_jk : instance of ndarray
            The (N_datasets,N_sources)-shaped numpy ndarray holding the
            source detector signal yield weight for each combination of
            dataset and source.
        a_jk_grads : dict
            The dictionary holding the (N_datasets,N_sources)-shaped numpy
            ndarray with the derivatives w.r.t. the global fit parameter
            the SrcDetSigYieldWeightsService depend on. The dictionary's key
            is the index of the global fit parameter.
        """
        return (self._a_jk, self._a_jk_grads)


class DatasetSignalWeightFactorsService(object):
    r"""This class provides a service to calculates the dataset signal weight
    factors, :math:`f_j(\vec{p}_\mathrm{s})`, for each dataset.
    It utilizes the source detector signal yield weights
    :math:`a_{j,k}(\vec{p}_{\mathrm{s}_k})`, provided by the
    :class:`~SrcDetSigYieldWeightsService` class.
    """

    def __init__(self, src_detsigyield_weights_service):
        r"""Creates a new DatasetSignalWeightFactors instance.

        Parameters
        ----------
        src_detsigyield_weights_service : instance of SrcDetSigYieldWeightsService
            The instance of SrcDetSigYieldWeightsService providing the source
            detector signal yield weights
            :math:`a_{j,k}(\vec{p}_{\mathrm{s}_k})`.
        """
        self.src_detsigyield_weights_service = src_detsigyield_weights_service

    @property
    def src_detsigyield_weights_service(self):
        r"""The instance of SrcDetSigYieldWeightsService providing the source
        detector signal yield weights :math:`a_{j,k}(\vec{p}_{\mathrm{s}_k})`.
        """
        return self._src_detsigyield_weights_service

    @src_detsigyield_weights_service.setter
    def src_detsigyield_weights_service(self, service):
        if not isinstance(service, SrcDetSigYieldWeightsService):
            raise TypeError(
                'The src_detsigyield_weights_service property must be an '
                'instance of SrcDetSigYieldWeightsService!')
        self._src_detsigyield_weights_service = service

    @property
    def n_datasets(self):
        """(read-only) The number of datasets.
        """
        return self._src_detsigyield_weights_service.n_datasets

    def calculate(self):
        r"""Calculates the dataset signal weight factors,
        :math:`f_j(\vec{p}_\mathrm{s})`. The result is stored internally as:

            f_j : instance of ndarray
                The (N_datasets,)-shaped 1D numpy ndarray holding the dataset
                signal weight factor for each dataset.
            f_j_grads : dict
                The dictionary holding the (N_datasets,)-shaped numpy
                ndarray with the derivatives w.r.t. the global fit parameter
                the DatasetSignalWeightFactorsService depend on.
                The dictionary's key is the index of the global fit parameter.
        """
        (a_jk, a_jk_grads) = self._src_detsigyield_weights_service.get_weights()

        a_j = np.sum(a_jk, axis=1)
        a = np.sum(a_jk)

        self._f_j = a_j / a

        # Calculate the derivative of f_j w.r.t. all floating parameters present
        # in the a_jk_grads using the quotient rule of differentation.
        self._f_j_grads = dict()
        for gpidx in a_jk_grads.keys():
            # a is a scalar.
            # a_j is a (N_datasets)-shaped ndarray.
            # a_jk_grads is a dict of length N_gfl_params with values of
            #    (N_datasets,N_sources)-shaped ndarray.
            # a_j_grads is a (N_datasets,)-shaped ndarray.
            # a_grads is a scalar.
            a_j_grads = np.sum(a_jk_grads[gpidx], axis=1)
            a_grads = np.sum(a_jk_grads[gpidx])
            self._f_j_grads[gpidx] = (a_j_grads * a - a_j * a_grads) / a**2

    def get_weights(self):
        """Returns the

        Returns
        -------
        f_j : instance of ndarray
            The (N_datasets,)-shaped 1D numpy ndarray holding the dataset
            signal weight factor for each dataset.
        f_j_grads : dict
            The dictionary holding the (N_datasets,)-shaped numpy
            ndarray with the derivatives w.r.t. the global fit parameter
            the DatasetSignalWeightFactorsService depend on.
            The dictionary's key is the index of the global fit parameter.
        """
        return (self._f_j, self._f_j_grads)
