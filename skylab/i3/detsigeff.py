# -*- coding: utf-8 -*-

import abc
import numpy as np

import scipy.interpolate

from skylab.core import multiproc
from skylab.core.py import issequenceof
from skylab.core.binning import BinningDefinition
from skylab.core.detsigeff import DetSigEffImplMethod
from skylab.core.livetime import Livetime
from skylab.physics.flux import FluxModel, PowerLawFlux
from skylab.physics.flux import get_conversion_factor_to_internal_flux_unit


class I3PointLikeSourceDetSigEffImplMethod(DetSigEffImplMethod):
    """Abstract base class for all IceCube specific detector signal efficiency
    implementation methods. All IceCube detector signal efficiency
    implementation methods require a sinDec binning definition for the effective
    area.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, sinDec_binning):
        """Initializes a new detector signal efficiency implementation method
        object. It takes a sin(dec) binning definition.

        Parameters
        ----------
        sinDec_binning : BinningDefinition
            The BinningDefinition instance defining the sin(dec) binning that
            should be used to compute the sin(dec) dependency of the detector
            effective area.
        """
        self.sinDec_binning = sinDec_binning

    @property
    def livetime(self):
        """The integrated live-time in days.
        """
        return self._livetime
    @livetime.setter
    def livetime(self, lt):
        if(isinstance(lt, Livetime)):
            lt = lt.livetime
        if(not isinstance(lt, float)):
            raise TypeError('The livetime property must be of type float or an instance of Livetime!')
        self._livetime = lt

    @property
    def sinDec_binning(self):
        """The BinningDefinition instance for the sin(dec) binning that should
        be used for computing the sin(dec) dependency of the detector signal
        efficiency.
        """
        return self._sinDec_binning
    @sinDec_binning.setter
    def sinDec_binning(self, binning):
        if(not isinstance(binning, BinningDefinition)):
            raise TypeError('The sinDec_binning property must be an instance of BinningDefinition!')
        self._sinDec_binning = binning

    def construct(self, data_mc, fluxmodel, livetime):
        super(I3PointLikeSourceDetSigEffImplMethod, self).construct(
            data_mc, fluxmodel, livetime)

        # Set the livetime property, which will convert a Livetime instance into
        # a float with the integrated live-time.
        self.livetime = livetime

    def source_to_array(self, source):
        """Converts the sequence of PointLikeSource sources into a numpy record
        array holding the spatial information of the sources needed for the
        detector signal efficiency calculation.

        Parameters
        ----------
        source : SourceModel | sequence of SourceModel
            The source model containing the spatial information of the source.

        Returns
        -------
        arr : numpy record ndarray
            The generated numpy record ndarray holding the spatial information
            for each source.
        """
        sources = list(source)
        if(not issequenceof(sources, PointLikeSource)):
            raise TypeError('The source argument must be an instance of PointLikeSource!')

        arr = np.empty((len(sources),), dtype=[('dec', np.float)])
        for (i, src) in enumerate(sources):
            arr['dec'][i] = src.dec

        return arr


class I3PointLikeSourceFixedFluxDetSigEff(I3PointLikeSourceDetSigEffImplMethod):
    """This detector signal efficiency implementation method constructs a
    detector signal efficiency for a fixed flux model, assuming a point-like
    source. This means that the detector signal efficiency does not depend on
    any source flux parameters, hence it is only dependent on the detector
    effective area.
    It constructs a one-dimensional spline function in sin(dec), using a
    scipy.interpolate.InterpolatedUnivariateSpline.

    This detector signal efficiency implementation method works with all flux
    models.

    It is tailored to the IceCube detector at the South Pole, where the
    effective area depends soley on the zenith angle, and hence on the
    declination, of the source.
    """
    def __init__(self, sinDec_binning, spline_order_sinDec=2):
        """Creates a new IceCube detector signal efficiency implementation
        method object for a fixed flux model. It requires a sinDec binning
        definition to compute the sin(dec) dependency of the detector effective
        area. The construct class method of this implementation method will
        create a spline function of a given order in logarithmic space of the
        effective area.

        Parameters
        ----------
        sinDec_binning : BinningDefinition
            The BinningDefinition instance which defines the sin(dec) binning.
        spline_order_sinDec : int
            The order of the spline function for the logarithmic values of the
            detector signal efficiency along the sin(dec) axis.
            The default is 2.
        """
        super(I3FixedFluxDetSigEff, self).__init__(sinDec_binning)

        self.supported_fluxmodels = (FluxModel,)

        self.spline_order_sinDec = spline_order_sinDec

    @property
    def spline_order_sinDec(self):
        """The order (int) of the logarithmic spline function, that splines the
        detector signal efficiency, along the sin(dec) axis.
        """
        return self._spline_order_sinDec
    @spline_order_sinDec.setter
    def spline_order_sinDec(self, order):
        if(not isinstance(order, int)):
            raise TypeError('The spline_order_sinDec property must be of type int!')
        self._spline_order_sinDec = order

    def construct(self, data_mc, fluxmodel, livetime):
        """Constructs a detector signal efficiency log spline function for the
        given fixed flux model.

        Parameters
        ----------
        data_mc : ndarray
            The numpy record ndarray holding the monte-carlo event data.
            The following data fields must exist:
            'true_dec' : float
                The true declination of the data event.
            'true_energy' : float
                The true energy value of the data event.
            'mcweight' : float
                The monte-carlo weight of the data event in the unit
                GeV cm^2 sr.
        fluxmodel : FluxModel
            The flux model instance. Must be an instance of FluxModel.
        livetime : float | Livetime
            The live-time in days to use for the detector signal efficiency.
        """
        super(I3FixedFluxDetSigEff, self).construct(data_mc, fluxmodel, livetime)

        # Calculate conversion factor from the flux model unit into the internal
        # flux unit GeV^-1 cm^-2 s^-1.
        toGeVcm2s = get_conversion_factor_to_internal_flux_unit(fluxmodel)

        # Calculate the detector signal efficiency contribution of each event.
        # The unit of mcweight is assumed to be GeV cm^2 sr.
        w = data_mc["mcweight"] * fluxmodel(data_mc["true_energy"])*toGeVcm2s * self._livetime * 86400.

        # Create a histogram along sin(true_dec).
        (h, bins) = np.histogram(np.sin(mc["true_dec"]),
                                 weights = w,
                                 bins = self.sinDec_binning.binedges,
                                 density = False)

        # Normalize by solid angle of each bin which is
        # 2*\pi*(\Delta sin(\delta)).
        h /= (2.*np.pi * np.diff(self.sinDec_binning.binedges))

        # Create spline in ln(h) at the histogram's bin centers.
        self._log_spl_sinDec = scipy.interpolate.InterpolatedUnivariateSpline(
            self.sinDec_binning.bincenters, np.log(h), k=self.spline_order_sinDec)

    def get(self, src, src_flux_params=None):
        """Retrieves the detector signal efficiency for the list of given
        sources.

        Parameters
        ----------
        src : numpy record ndarray
            The numpy record ndarray with the field ``dec`` holding the
            declination of the source.
        src_flux_params : None
            Unused interface argument, because this implementation does not
            depend on any source flux fit parameters.

        Returns
        -------
        values : numpy 1d ndarray
            The array with the detector signal efficiency for each source.
        grads : None
            Because with this implementation the detector signal efficiency
            does not depend on any fit parameters. So there are no gradients
            and None is returned.
        """
        src_dec = np.atleast_1d(src['dec'])

        # Create results array.
        values = np.zeros_like(src_dec, dtype=np.float64)

        # Create mask for all source declinations which are inside the
        # declination range.
        mask = (np.sin(src_dec) >= self.sinDec_binning.lower_edge)\
              &(np.sin(src_dec) <= self.sinDec_binning.upper_edge)

        values[mask] = np.exp(self._log_spl_sinDec(np.sin(src_dec[mask])))

        return (values, None)


class I3PointLikeSourcePowerLawFluxDetSigEff(I3PointLikeSourceDetSigEffImplMethod, multiproc.IsParallelizable):
    """This detector signal efficiency implementation method constructs a
    detector signal efficiency for a variable power law flux model, which has
    the spectral index gamma as fit parameter, assuming a point-like source.
    It constructs a two-dimensional spline function in sin(dec) and gamma, using
    a scipy.interpolate.RectBivariateSpline. Hence, the detector signal
    efficiency can vary with the declination and the spectral index, gamma, of
    the source.

    This detector signal efficiency implementation method works with a
    PowerLawFlux flux model.

    It is tailored to the IceCube detector at the South Pole, where the
    effective area depends soley on the zenith angle, and hence on the
    declination, of the source.
    """
    def __init__(self, sinDec_binning, gamma_binning,
                 spline_order_sinDec=2, spline_order_gamma=2, ncpu=None):
        """Creates a new IceCube detector signal efficiency implementation
        method object for a power law flux model. It requires a sinDec binning
        definition to compute the sin(dec) dependency of the detector effective
        area, and a gamma value binning definition to compute the gamma
        dependency of the detector signal efficiency.

        Parameters
        ----------
        sinDec_binning : BinningDefinition
            The BinningDefinition instance which defines the sin(dec) binning.
        gamma_binning : BinningDefinition
            The BinningDefinition instance which defines the gamma binning.
        spline_order_sinDec : int
            The order of the spline function for the logarithmic values of the
            detector signal efficiency along the sin(dec) axis.
            The default is 2.
        spline_order_gamma : int
            The order of the spline function for the logarithmic values of the
            detector signal efficiency along the gamma axis.
            The default is 2.
        ncpu : int | None
            The number of CPUs to utilize. Global setting will take place if
            not specified, i.e. set to None.
        """
        super(I3PowerLawFluxDetSigEff, self).__init__(sinDec_binning)

        self.supported_fluxmodels = (PowerLawFlux,)

        self.gamma_binning = gamma_binning
        self.spline_order_sinDec = spline_order_sinDec
        self.spline_order_gamma = spline_order_gamma
        self.ncpu = ncpu

    @property
    def gamma_binning(self):
        """The BinningDefinition instance for the gamma binning that should be
        used for computing the gamma dependency of the detector signal
        efficiency.
        """
        return self._gamma_binning
    @gamma_binning.setter
    def gamma_binning(self, binning):
        if(not isinstance(binning, BinningDefinition)):
            raise TypeError('The gamma_binning property must be an instance of BinningDefinition!')
        self._gamma_binning = binning

    @property
    def spline_order_sinDec(self):
        """The order (int) of the logarithmic spline function, that splines the
        detector signal efficiency, along the sin(dec) axis.
        """
        return self._spline_order_sinDec
    @spline_order_sinDec.setter
    def spline_order_sinDec(self, order):
        if(not isinstance(order, int)):
            raise TypeError('The spline_order_sinDec property must be of type int!')
        self._spline_order_sinDec = order

    @property
    def spline_order_gamma(self):
        """The order (int) of the logarithmic spline function, that splines the
        detector signal efficiency, along the gamma axis.
        """
        return self._spline_order_gamma
    @spline_order_gamma.setter
    def spline_order_gamma(self, order):
        if(not isinstance(order, int)):
            raise TypeError('The spline_order_gamma property must be of type int!')
        self._spline_order_gamma = order

    def _get_signal_fitparam_names(self):
        """The list of signal fit parameter names the detector signal efficiency
        depends on.
        """
        return ['gamma']

    def construct(self, data_mc, fluxmodel, livetime):
        """Constructs a detector signal efficiency 2-dimensional log spline
        function for the given power law flux model with varying gamma values.

        Parameters
        ----------
        data_mc : ndarray
            The numpy record ndarray holding the monte-carlo event data.
            The following data fields must exist:
            'true_dec' : float
                The true declination of the data event.
            'mcweight' : float
                The monte-carlo weight of the data event in the unit
                GeV cm^2 sr.
            'true_energy' : float
                The true energy value of the data event.
        fluxmodel : FluxModel
            The flux model instance. Must be an instance of FluxModel.
        livetime : float | Livetime
            The live-time in days to use for the detector signal efficiency.
        """
        super(I3PowerLawFluxDetSigEff, self).construct(data_mc, fluxmodel, livetime)

        # Calculate conversion factor from the flux model unit into the internal
        # flux unit GeV^-1 cm^-2 s^-1.
        toGeVcm2s = get_conversion_factor_to_internal_flux_unit(fluxmodel)

        # Define a function that creates a detector signal efficiency histogram
        # along sin(dec) for a given flux model, i.e. for given spectral index,
        # gamma.
        def hist(data_sin_true_dec, data_true_energy, sinDec_binning, weights, fluxmodel):
            """Creates a histogram of the detector signal efficiency with the
            given sin(dec) binning.

            Parameters
            ----------
            data_sin_true_dec : 1d ndarray
                The sin(true_dec) values of the monte-carlo events.
            data_true_energy : 1d ndarray
                The true energy of the monte-carlo events.
            sinDec_binning : BinningDefinition
                The sin(dec) binning definition to use for the histogram.
            weights : 1d ndarray
                The weight factors of each monte-carlo event where only the
                flux value needs to be multiplied with in order to get the
                detector signal efficiency.
            fluxmodel : FluxModel
                The flux model to get the flux values from.

            Returns
            -------
            h : 1d ndarray
                The numpy array containing the histogram values.
            """
            (h, edges) = np.histogram(data_sin_true_dec,
                                      bins = sinDec_binning.binedges,
                                      weights = weights * fluxmodel(data_true_energy),
                                      density = False)
            return h

        data_sin_true_dec = np.sin(data_mc["true_dec"])
        weights = data_mc["mcweight"] * toGeVcm2s * self._livetime * 86400.

        # Construct the arguments for the hist function to be used in the
        # multiproc.parallelize function.
        args_list = [ ((data_sin_true_dec, data_mc['true_energy'], self.sinDec_binning, weights, fluxmodel.copy({'gamma':gamma})),{})
                     for gamma in self.gamma_binning.binedges ]
        h = np.vstack(multiproc.parallelize(hist, args_list, self.ncpu)).T

        # Normalize by solid angle of each bin along the sin(dec) axis.
        # The solid angle is given by 2*\pi*(\Delta sin(\delta))
        h /= (2.*np.pi * np.diff(self.sinDec_binning.binedges)).reshape((self.sinDec_binning.nbins,1))

        self._log_spl_sinDec_gamma = scipy.interpolate.RectBivariateSpline(
            self.sinDec_binning.bincenters, self.gamma_binning.binedges, np.log(h),
            kx = self.spline_order_sinDec, ky = self.spline_order_gamma, s = 0)

    def get(self, src, src_flux_params):
        """Retrieves the detector signal efficiency for the given list of
        sources and their flux parameters.

        Parameters
        ----------
        src : numpy record ndarray
            The numpy record ndarray with the field ``dec`` holding the
            declination of the source.
        src_flux_params : numpy record ndarray
            The numpy record ndarray containing the flux parameter ``gamma`` for
            the sources. ``gamma`` can be different for the different sources.

        Returns
        -------
        values : numpy (N_sources,)-shaped 1D ndarray
            The array with the detector signal efficiency for each source.
        grads : numpy (N_sources,N_fitparams)-shaped 2D ndarray
            The array containing the gradient values for each source and fit
            parameter. Since, this implementation depends on only one fit
            parameter, i.e. gamma, the array is (N_sources,1)-shaped.
        """
        src_dec = np.atleast_1d(src['dec'])
        src_gamma = src_flux_params['gamma']

        # Create results array.
        values = np.zeros_like(src_dec, dtype=np.float)
        grads = np.zeros_like(src_dec, dtype=np.float)

        # Calculate the detector signal efficiency only for the sources for
        # which we actually have efficiency. For the other sources, the detector
        # signal efficiency is zero.
        mask = (np.sin(src_dec) >= self.sinDec_binning.lower_edge)\
              &(np.sin(src_dec) <= self.sinDec_binning.upper_edge)

        values[mask] = np.exp(self._log_spl_sinDec_gamma(np.sin(src_dec[mask]), src_gamma[mask], grid=False))
        grads[mask] = values[mask] * self._log_spl_sinDec_gamma(np.sin(src_dec[mask]), src_gamma[mask], grid=False, dy=1)

        return (values, np.atleast_2d(grads))
