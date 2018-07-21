# -*- coding: utf-8 -*-

"""The ``signalpdf`` module contains possible signal PDF models for the
likelihood function.
"""

import numpy as np

from skylab.core.pdf import SpatialPDF, IsSignalPDF
from skylab.physics.source import PointLikeSource, PointLikeSourceCollection

class GaussianPSFPointLikeSourceSignalSpatialPDF(SpatialPDF, IsSignalPDF):
    """This spatial signal PDF model describes the spatial PDF for a point
    source smeared with a 2D gaussian point-spread-function (PSF).
    Mathematically, it's the convolution of a point in the sky, i.e. the source
    location, with the PSF. The result of this convolution has the gaussian form

        1/(2*\pi*\sigma^2) * exp(-1/2*(r / \sigma)**2),

    where \sigma is the spatial uncertainty of the event and r the distance on
    the sphere between the source and the data event.
    """
    def __init__(self, sources):
        """Creates a new spatial signal PDF for point-like sources with a
        gaussian PSF.

        Parameters
        ----------
        sources : PointLikeSource | PointLikeSourceCollection
            The instance of PointLikeSourceCollection containing the
            PointLikeSource objects for which the spatial PDF values should get
            calculated for.
        """
        super(GaussianPSFPointLikeSourceSignalSpatialPDF, self).__init__(
            ra_range=(0, 2*np.pi),
            dec_range=(-np.pi/2, np.pi/2))

        if(isinstance(sources, PointLikeSource)):
            sources = PointLikeSourceCollection([sources])
        if(not isinstance(sources, PointLikeSourceCollection)):
            raise TypeError('The sources argument must be an instance of PointLikeSourceCollection!')

        # For the calculation ndarrays for the right-ascention and declination
        # of the different point-like sources is more efficient.
        self.src_ra = np.array([ src.ra for src in sources ])
        self.src_dec = np.array([ src.dec for src in sources ])

    def get_prob(self, events, params=None):
        """Calculates the spatial signal probability of each event for all given
        sources.

        Parameters
        ----------
        events : numpy record ndarray
            The numpy record array holding the event data. The following data
            fields need to be present:

            'ra' : float
                The right-ascention in radian of the data event.
            'dec' : float
                The declination in radian of the data event.
            'sigma': float
                The reconstruction uncertainty in radian of the data event.
        params : None
            Unused interface argument.

        Returns
        -------
        prob : (N_sources,N_events) shaped 2D ndarray
            The ndarray holding the spatial signal probability on the sphere for
            each source and event.
        """
        ra = events['ra']
        dec = events['dec']
        sigma = events['sigma']

        # Make the source position angles two-dimensional so the PDF value can
        # be calculated via numpy broadcasting automatically for several
        # sources. This is useful for stacking analyses.
        src_ra = self.src_ra[:,np.newaxis]
        src_dec = self.src_dec[:,np.newaxis]

        # Calculate the cosine of the distance of the source and the event on
        # the sphere.
        cos_r = np.cos(src_ra - ra) * np.cos(src_dec) * np.cos(dec) + np.sin(src_dec) * np.sin(dec)

        # Handle possible floating precision errors.
        cos_r[cos_r < -1.] = -1.
        cos_r[cos_r > 1.] = 1.
        r = np.arccos(cos_r)

        prob = 0.5/(np.pi*sigma**2) * np.exp(-0.5*(r / sigma)**2)

        return prob
