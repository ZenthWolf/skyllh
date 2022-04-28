import numpy as np

from skyllh.core.llhratio import LLHRatio
from skyllh.core.dataset import Dataset
from skyllh.core.source_hypothesis import SourceHypoGroupManager
from skyllh.core.storage import DataFieldRecordArray
from skyllh.analyses.i3.trad_ps.utils import (
    psi_to_dec_and_ra,
    PublicDataSmearingMatrix
)
from skyllh.core.py import (
    issequenceof,
    float_cast,
    int_cast
)


class PublicDataDatasetSignalGenerator(object):

    def __init__(self, ds, **kwargs):
        """Creates a new instance of the signal generator for generating signal
        events from the provided public data dataset.
        """
        super().__init__(**kwargs)

        self.smearing_matrix = PublicDataSmearingMatrix(
            pathfilenames=ds.get_abs_pathfilename_list(
                ds.get_aux_data_definition('smearing_datafile')))

    def _generate_events(
            self, rss, src_dec, src_ra, dec_idx, flux_model, n_events):
        """Generates `n_events` signal events for the given source location
        and flux model.

        Note:
            Some values can be NaN in cases where a PDF was not available!

        Parameters
        ----------
        rss : instance of RandomStateService
            The instance of RandomStateService to use for drawing random
            numbers.
        src_dec : float
            The declination of the source in radians.
        src_ra : float
            The right-ascention of the source in radians.

        Returns
        -------
        events : numpy record array of size `n_events`
            The numpy record array holding the event data.
            It contains the following data fields:
                - 'isvalid'
                - 'log_true_energy'
                - 'log_energy'
                - 'sin_dec'
            Single values can be NaN in cases where a pdf was not available.
        """

        # Create the output event DataFieldRecordArray.
        out_dtype = [
            ('isvalid', np.bool_),
            ('log_true_energy', np.double),
            ('log_energy', np.double),
            ('dec', np.double),
            ('ra', np.double),
            ('sin_dec', np.double),
            ('ang_err', np.double),
            ('time', int),
            ('azi', np.double),
            ('zen', np.double),
            ('run', int)
        ]

        data = dict(
            [(out_dt[0], np.empty(
                (n_events,),
                dtype=out_dt[1])
              ) for out_dt in out_dtype]
        )

        events = DataFieldRecordArray(data, copy=False)

        sm = self.smearing_matrix

        # Determine the true energy range for which log_e PDFs are available.
        (min_log_true_e,
         max_log_true_e) = sm.get_true_log_e_range_with_valid_log_e_pfds(
             dec_idx)

        # First draw a true neutrino energy from the hypothesis spectrum.
        log_true_e = np.log10(flux_model.get_inv_normed_cdf(
            rss.random.uniform(size=n_events),
            E_min=10**min_log_true_e,
            E_max=10**max_log_true_e
        ))

        events['log_true_energy'] = log_true_e

        log_true_e_idxs = (
            np.digitize(log_true_e, bins=sm.true_e_bin_edges) - 1
        )
        # Sample reconstructed energies given true neutrino energies.
        (log_e_idxs, log_e) = sm.sample_log_e(
            rss, dec_idx, log_true_e_idxs)
        events['log_energy'] = log_e

        # Sample reconstructed psi values given true neutrino energy and
        # reconstructed energy.
        (psi_idxs, psi) = sm.sample_psi(
            rss, dec_idx, log_true_e_idxs, log_e_idxs)

        # Sample reconstructed ang_err values given true neutrino energy,
        # reconstructed energy, and psi.
        (ang_err_idxs, ang_err) = sm.sample_ang_err(
            rss, dec_idx, log_true_e_idxs, log_e_idxs, psi_idxs)

        isvalid = np.invert(
            np.isnan(log_e) | np.isnan(psi) | np.isnan(ang_err))
        events['isvalid'] = isvalid

        # Convert the psf into a set of (r.a. and dec.). Only use non-nan
        # values.
        (dec, ra) = psi_to_dec_and_ra(rss, src_dec, src_ra, psi[isvalid])
        events['ra'][isvalid] = ra
        events['dec'][isvalid] = dec
        events['sin_dec'][isvalid] = np.sin(dec)

        # Add an angular error. Only use non-nan values.
        events['ang_err'][isvalid] = ang_err

        # Add fields required by the framework
        events['time'] = np.ones(n_events)
        events['azi'] = np.ones(n_events)
        events['zen'] = np.ones(n_events)
        events['run'] = -1 * np.ones(n_events)

        return events

    def generate_signal_events(
            self, rss, src_dec, src_ra, flux_model, n_events):
        """Generates ``n_events`` signal events for the given source location
        and flux model.

        Returns
        -------
        events : numpy record array
            The numpy record array holding the event data.
            It contains the following data fields:
                - 'isvalid'
                - 'log_true_energy'
                - 'log_energy'
                - 'dec'
                - 'ra'
                - 'ang_err'
        """
        sm = self.smearing_matrix

        # Find the declination bin index.
        dec_idx = sm.get_true_dec_idx(src_dec)

        events = None
        n_evt_generated = 0
        while n_evt_generated != n_events:
            n_evt = n_events - n_evt_generated

            events_ = self._generate_events(
                rss, src_dec, src_ra, dec_idx, flux_model, n_evt)

            # Cut events that failed to be generated due to missing PDFs.
            events_ = events_[events_['isvalid']]

            n_evt_generated += len(events_)
            if events is None:
                events = events_
            else:
                events = np.concatenate((events, events_))

        return events


class PublicDataSignalGenerator(object):
    """This class provides a signal generation method for a point-like source
    seen in the IceCube detector using the 10 years public data release.
    """

    def __init__(self, src_hypo_group_manager, dataset_list, data_list=None, llhratio=None):
        self.src_hypo_group_manager = src_hypo_group_manager
        self.dataset_list = dataset_list
        self.data_list = data_list
        self.llhratio = llhratio

        self.sig_gen_list = []
        for ds in self._dataset_list:
            self.sig_gen_list.append(PublicDataDatasetSignalGenerator(ds))

    @property
    def src_hypo_group_manager(self):
        """The SourceHypoGroupManager instance defining the source groups with
        their spectra.
        """
        return self._src_hypo_group_manager

    @src_hypo_group_manager.setter
    def src_hypo_group_manager(self, manager):
        if(not isinstance(manager, SourceHypoGroupManager)):
            raise TypeError('The src_hypo_group_manager property must be an '
                            'instance of SourceHypoGroupManager!')
        self._src_hypo_group_manager = manager

    @property
    def dataset_list(self):
        """The list of Dataset instances for which signal events should get
        generated for.
        """
        return self._dataset_list

    @dataset_list.setter
    def dataset_list(self, datasets):
        if(not issequenceof(datasets, Dataset)):
            raise TypeError('The dataset_list property must be a sequence of '
                            'Dataset instances!')
        self._dataset_list = list(datasets)

    @property
    def llhratio(self):
        """The log-likelihood ratio function for the analysis.
        """
        return self._llhratio

    @llhratio.setter
    def llhratio(self, llhratio):
        if llhratio is not None:
            if(not isinstance(llhratio, LLHRatio)):
                raise TypeError('The llratio property must be an instance of '
                                'LLHRatio!')
        self._llhratio = llhratio

    def generate_signal_events(self, rss, mean, poisson=True):
        shg_list = self._src_hypo_group_manager.src_hypo_group_list

        tot_n_events = 0
        signal_events_dict = {}

        for shg in shg_list:
            # This only works with power-laws for now.
            # Each source hypo group can have a different power-law
            gamma = shg.fluxmodel.gamma
            weights, _ = self.llhratio.dataset_signal_weights([mean, gamma])
            src_list = shg.source_list
            for (ds_idx, (sig_gen, w)) in enumerate(zip(self.sig_gen_list, weights)):
                w_mean = mean * w
                if(poisson):
                    n_events = rss.random.poisson(
                        float_cast(
                            w_mean,
                            '`mean` must be castable to type of float!'
                        )
                    )
                else:
                    n_events = int_cast(
                        w_mean,
                        '`mean` must be castable to type of float!'
                    )
                tot_n_events += n_events

                events_ = None
                for (shg_src_idx, src) in enumerate(src_list):
                    # ToDo: here n_events should be split according to some
                    # source weight
                    events_ = sig_gen.generate_signal_events(
                        rss,
                        src.dec,
                        src.ra,
                        shg.fluxmodel,
                        n_events
                    )
                    if events_ is None:
                        continue

                    if shg_src_idx == 0:
                        signal_events_dict[ds_idx] = events_
                    else:
                        signal_events_dict[ds_idx].append(events_)

        return tot_n_events, signal_events_dict
