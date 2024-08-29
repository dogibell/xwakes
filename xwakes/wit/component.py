from __future__ import annotations

from .interface_dataclasses import Layer, FlatIW2DInput, RoundIW2DInput
from .parameters import *
from .utils import unique_sigfigs
from typing import Optional, Callable, Tuple, Union, List

import numpy as np
from scipy.constants import c as c_light, mu_0 as mu0, epsilon_0 as eps0
from numpy.typing import ArrayLike
from scipy import special as sp

if hasattr(np, 'trapezoid'):
    trapz = np.trapezoid # numpy 2.0
else:
    trapz = np.trapz

Z0 = mu0 * c_light

KIND_DEFINITIONS = {
    'longitudinal':   {'plane': 'z', 'source_exponents':(0, 0), 'test_exponents': (0, 0)},
     'constant_x':    {'plane': 'x', 'source_exponents':(0, 0), 'test_exponents': (0, 0)},
     'constant_y':    {'plane': 'y', 'source_exponents':(0, 0), 'test_exponents': (0, 0)},
     'dipolar_x':      {'plane': 'x', 'source_exponents':(1, 0), 'test_exponents': (0, 0)},
     'dipolar_y':      {'plane': 'y', 'source_exponents':(0, 1), 'test_exponents': (0, 0)},
     'dipolar_xy':     {'plane': 'x', 'source_exponents':(0, 1), 'test_exponents': (0, 0)},
     'dipolar_yx':     {'plane': 'y', 'source_exponents':(1, 0), 'test_exponents': (0, 0)},
     'quadrupolar_x':  {'plane': 'x', 'source_exponents':(0, 0), 'test_exponents': (1, 0)},
     'quadrupolar_y':  {'plane': 'y', 'source_exponents':(0, 0), 'test_exponents': (0, 1)},
     'quadrupolar_xy': {'plane': 'x', 'source_exponents':(0, 0), 'test_exponents': (0, 1)},
     'quadrupolar_yx': {'plane': 'y', 'source_exponents':(0, 0), 'test_exponents': (1, 0)},
     'dipole_x':      {'plane': 'x', 'source_exponents':(1, 0), 'test_exponents': (0, 0)},
     'dipole_y':      {'plane': 'y', 'source_exponents':(0, 1), 'test_exponents': (0, 0)},
     'dipole_xy':     {'plane': 'x', 'source_exponents':(0, 1), 'test_exponents': (0, 0)},
     'dipole_yx':     {'plane': 'y', 'source_exponents':(1, 0), 'test_exponents': (0, 0)},
     'quadrupole_x':  {'plane': 'x', 'source_exponents':(0, 0), 'test_exponents': (1, 0)},
     'quadrupole_y':  {'plane': 'y', 'source_exponents':(0, 0), 'test_exponents': (0, 1)},
     'quadrupole_xy': {'plane': 'x', 'source_exponents':(0, 0), 'test_exponents': (0, 1)},
     'quadrupole_yx': {'plane': 'y', 'source_exponents':(0, 0), 'test_exponents': (1, 0)},
}


def mix_fine_and_rough_sampling(start: float, stop: float, rough_points: int,
                                fine_points: int, rois: List[Tuple[float, float]]):
    """
    Mix a fine and rough (geometric) sampling between start and stop,
    refined in the regions of interest rois.
    :param start: The lowest bound of the sampling
    :param stop: The highest bound of the sampling
    :param rough_points: The total number of data points to be
                         generated for the rough grid, between start
                         and stop.
    :param fine_points: The number of points in the fine grid of each roi.
    :param rois: List of unique tuples with the lower and upper bound of
                 of each region of interest.
    :return: An array with the sampling obtained.
    """
    intervals = [np.linspace(max(i, start), min(f, stop), fine_points)
                 for i, f in rois
                 if (start <= i <= stop or start <= f <= stop)]
    rough_sampling = np.geomspace(start, stop, rough_points)
    # the following concatenates adds the rough points to the fine sampling and sorts
    # the result. Then duplicates are removed, where two points are considered
    # equal if they are within 7 significant figures of each other.
    return unique_sigfigs(
        np.sort(np.hstack((*intervals, rough_sampling)),kind='stable'), 7)


class Component:
    """
    A data structure representing the impedance- and wake functions of some Component in a specified plane.
    """

    def __init__(self, impedance: Optional[Callable] = None, wake: Optional[Callable] = None,
                 plane: str = None,
                 source_exponents: Tuple[int, int] = (-1, -1), test_exponents: Tuple[int, int] = (-1, -1),
                 kind: str = None,
                 name: str = "Unnamed Component", f_rois: Optional[List[Tuple[float, float]]] = None,
                 t_rois: Optional[List[Tuple[float, float]]] = None):
        """
        The initialization function for the Component class.
        :param impedance: A callable function representing the impedance function of the Component. Can be undefined if
        the wake function is defined.
        :param wake: A callable function representing the wake function of the Component. Can be undefined if
        the impedance function is defined.
        :param plane: The plane of the Component, either 'x', 'y' or 'z'. Must be specified for valid initialization
        :param source_exponents: The exponents in the x and y planes experienced by the source particle. Also
        referred to as 'a' and 'b'. Must be specified for valid initialization
        :param test_exponents: The exponents in the x and y planes experienced by the source particle. Also
        referred to as 'a' and 'b'. Must be specified for valid initialization
        :param name: An optional user-specified name of the component
        """

        assert (kind in KIND_DEFINITIONS,
                f"Invalid kind specified: {kind}. Must be one of {KIND_DEFINITIONS.keys()}")

        source_exponents, test_exponents, plane = _handle_plane_and_exponents_input(
                                    kind=kind, exponents=None,
                                    source_exponents=source_exponents,
                                    test_exponents=test_exponents,
                                    plane=plane)

        # Enforces that either impedance or wake is defined.
        assert impedance or wake, "The impedance- and wake functions cannot both be undefined."
        # The impedance- and wake functions as callable objects, e.g lambda functions
        self._impedance = impedance
        self._wake = wake
        self.name = name

        # The plane of the Component, either 'x', 'y' or 'z'
        assert plane.lower() in ['x', 'y', 'z'], (
            f"Invalid plane specified: {plane}. Must be 'x', 'y' or 'z'.")

        self.plane = plane

        assert source_exponents != (-1, -1) and len(source_exponents) == 2, \
            "Cannot initialize Component object without specified source exponents (a, b)"
        self.source_exponents = source_exponents
        assert test_exponents != (-1, -1) and len(test_exponents) == 2, \
            "Cannot initialize Component object without specified test exponents (c, d)"
        self.test_exponents = test_exponents
        self.power_x = (source_exponents[0] + test_exponents[0] + (plane == 'x')) / 2
        self.power_y = (source_exponents[1] + test_exponents[1] + (plane == 'y')) / 2
        self._f_rois = f_rois if f_rois else []
        self._t_rois = t_rois if t_rois else []

    @property
    def impedance(self) -> Optional[Callable]:
        return self._impedance

    @property
    def wake(self) -> Optional[Callable]:
        return self._wake

    @property
    def f_rois(self) -> List[Tuple[float, float]]:
        return self._f_rois

    @property
    def t_rois(self) -> List[Tuple[float, float]]:
        return self._t_rois

    def function_vs_t(self, t, beta0, dt):
        out = self.wake(t)
        return out

    def function_vs_zeta(self, zeta, beta0, dzeta):
        out = self.function_vs_t(-zeta / beta0 / c_light, beta0,
                                 dzeta / beta0 / c_light)
        return out

    @property
    def kick(self) -> str:
        return {'x': 'px', 'y': 'py', 'z': 'delta'}[self.plane]

    @property
    def source_moments(self) -> List[str]:
        out = ['num_particles']
        if self.source_exponents[0] != 0:
            out.append('x')
        if self.source_exponents[1] != 0:
            out.append('y')

        return out

    def generate_wake_from_impedance(self) -> None:
        """
        Uses the impedance function of the Component object to generate its wake function, using
        a Fourier transform.
        :return: Nothing
        """
        # # If the object already has a wake function, there is no need to generate it.
        # if self.wake:
        #     pass
        # # In order to generate a wake function, we need to make sure the impedance function is defined.
        # assert self.impedance, "Tried to generate wake from impedance, but impedance is not defined."
        #
        # raise NotImplementedError

        # Temporary solution to avoid crashes
        self.wake = lambda x: 0

    def generate_impedance_from_wake(self) -> None:
        """
        Uses the wake function of the Component object to generate its impedance function, using
        a Fourier transform.
        :return: Nothing
        """
        # # If the object already has an impedance function, there is no need to generate it.
        # if self.impedance:
        #     pass
        # # In order to generate an impedance function, we need to make sure the wake function is defined.
        # assert self.wake, "Tried to generate impedance from wake, but wake is not defined."
        #
        # raise NotImplementedError

        # Temporary solution to avoid crashes
        self.impedance = lambda x: 0

    def is_compatible(self, other: Component) -> bool:
        """
        Compares all parameters of the self-object with the argument of the function and returns True if all of their
        attributes, apart from the impedance and wake functions, are identical.
        i.e. Returns True if self and other are compatible for Component addition, False otherwise
        :param other: Another Component
        :return: True if self and other can be added together, False otherwise
        """
        if not isinstance(other, Component):
            return False

        return all([self.source_exponents == other.source_exponents,
                    self.test_exponents == other.test_exponents,
                    self.plane == other.plane,
                    self.power_x == other.power_x,
                    self.power_y == other.power_y])

    def configure_for_tracking(self, zeta_range: Tuple[float, float],
                               num_slices: int,
                               **kwargs # for multibuunch compatibility
                               ) -> None:
        import xfields as xf
        self._xfields_wf = xf.Wakefield(components=[self], zeta_range=zeta_range,
                                        num_slices=num_slices, **kwargs)

    def track(self, particles):

        if not hasattr(self, '_xfields_wf') or not self._xfields_wf:
            raise ValueError('The component has not been configured for tracking. '
                             'Call configure_for_tracking before calling track.')
        self._xfields_wf.track(particles)


    def __add__(self, other: Component) -> Component:
        """
        Defines the addition operator for two Components
        :param self: The left addend
        :param other: The right addend
        :return: A new Component whose impedance and wake functions are the sums
        of the respective functions of the two addends.
        """

        if not isinstance(other, Component):
            return other.__radd__(self)

        # Enforce that the two addends are in the same plane
        assert self.plane == other.plane, "The two addends correspond to different planes and cannot be added.\n" \
                                          f"{self.plane} != {other.plane}"

        # Enforce that the two addends have the same exponent parameters
        assert self.source_exponents == other.source_exponents and self.test_exponents == other.test_exponents, \
            "The two addends have different exponent parameters and cannot be added.\n" \
            f"Source: {self.source_exponents} != {other.source_exponents}\n" \
            f"Test: {self.test_exponents} != {other.test_exponents}"

        # Defines an empty array to hold the two summed functions
        sums = []

        # Iterates through the two pairs of functions: impedances, then wakes
        for left, right in zip((self.impedance, self.wake), (other.impedance, other.wake)):
            # If neither addend has a defined function, we will not bother to calculate that of the sum
            if (not left) and (not right):
                sums.append(None)
            else:
                # # Generates the missing function for the addend which is missing it
                # if not left:
                #     [self.generate_impedance_from_wake, self.generate_wake_from_impedance][len(sums)]()
                # elif not right:
                #     [other.generate_impedance_from_wake, other.generate_wake_from_impedance][len(sums)]()
                #

                # TODO: Temporary fix until Fourier transform implemented
                if not left:
                    sums.append(right)
                elif not right:
                    sums.append(left)
                else:
                    # Appends the sum of the functions of the two addends to the list "sums"
                    sums.append(lambda x, l=left, r=right: l(x) + r(x))

        # Initializes and returns a new Component
        return Component(impedance=sums[0], wake=sums[1],
                         plane=self.plane,
                         source_exponents=self.source_exponents,
                         test_exponents=self.test_exponents,
                         f_rois=self.f_rois + other.f_rois,
                         t_rois=self.t_rois + other.t_rois)

    def __radd__(self, other: Union[int, Component]) -> Component:
        """
        Implements the __radd__ method for the Component class. This is only done to facilitate the syntactically
        practical use of the sum() method for Components. sum(iterable) works by adding all of the elements of the
        iterable to 0 sequentially. Thus, the behavior of the initial 0 + iterable[0] needs to be defined. In the case
        that the left addend of any addition involving a Component is not itself a Component, the resulting sum
        is simply defined to be the right addend.
        :param other: The left addend of an addition
        :return: The sum of self and other if other is a Component, otherwise just self.
        """

        # Checks if the left addend, other, is not a Component
        if  isinstance(other, int):
            # In which case, the right addend is simply returned
            return self
        elif not isinstance(other, Component):
            return other.__add__(self)
        else:
        # Otherwise, their sum is returned (by invocation of Component.__add__(self, other))
            return self + other

    def __mul__(self, scalar: complex) -> Component:
        """
        Defines the behavior of multiplication of a Component by some, potentially complex, scalar
        :param scalar: A scalar value to be multiplied with some Component
        :return: A newly initialized Component identical to self in every way apart from the impedance-
        and wake functions, which have been multiplied by the scalar.
        """
        # Throws an AssertionError if scalar is not of the type complex, float or int
        assert isinstance(scalar, complex) or isinstance(scalar, float) or isinstance(scalar, int)
        # Initializes and returns a new Component with attributes like self, apart from the scaled functions
        return Component(impedance=(lambda x: scalar * self.impedance(x)) if self.impedance else None,
                         wake=(lambda x: scalar * self.wake(x)) if self.wake else None,
                         plane=self.plane,
                         source_exponents=self.source_exponents,
                         test_exponents=self.test_exponents, name=self.name,
                         f_rois=self.f_rois, t_rois=self.t_rois)

    def __rmul__(self, scalar: complex) -> Component:
        """
        Generalizes scalar multiplication of Component to be possibly from left and right. Both of these operations
        are identical.
        :param scalar: A scalar value to be multiplied with some Component
        :return: The result of calling Component.__mul__(self, scalar): A newly initialized Component identical to self
        in every way apart from the impedance- and wake functions, which have been multiplied by the scalar.
        """
        # Simply swaps the places of scalar and self in order to invoke the previously defined __mul__ function
        return self * scalar

    def __truediv__(self, scalar: complex) -> Component:
        """
        Implements the __truediv__ method for the Component class in order to produce the expected behavior when
        dividing a Component by some scalar. That is, the scalar multiplication of the multiplicative inverse of
        the scalar.
        :param scalar: A scalar value for the Component to be divided by
        :return: The result of calling Component.__mul__(self, 1 / scalar): A newly initialized Component identical to
        self in every way apart from the impedance- and wake functions, which have been multiplied by (1 / scalar).
        """
        # Defines the operation c / z to be equivalent to c * (1 / z) for some Component c and scalar z.
        return self * (1 / scalar)

    def __str__(self) -> str:
        """
        Implements the __str__ method for the Component class, providing an informative printout of the attributes
        of the Component.
        :return: A multi-line string containing information about the attributes of self, including which of the
        impedance- and wake functions are defined.
        """
        return f"{self.name} with parameters:\nPlane:\t\t\t{self.plane}\n" \
               f"Source exponents:\t{', '.join(str(i) for i in self.source_exponents)}\n" \
               f"Test exponents:\t\t{', '.join(str(i) for i in self.test_exponents)}\n" \
               f"Impedance function:\t{'DEFINED' if self.impedance else 'UNDEFINED'}\n" \
               f"Wake function:\t\t{'DEFINED' if self.wake else 'UNDEFINED'}\n" \
               f"Impedance-regions of interest: {', '.join(str(x) for x in self.f_rois)}\n" \
               f"Wake-regions of interest: {', '.join(str(x) for x in self.t_rois)}"

    def __lt__(self, other: Component) -> bool:
        """
        Implements the __lt__ (less than) method for the Component class. This has no real physical interpretation,
        it is just syntactically practical when iterating through the Components when adding two Elements.
        (see Element.__add__)
        :param other: The right hand side of a "<"-inequality
        :return: True if the self-Component is "less than" the other-Component by some arbitrary, but consistent,
        comparison.
        """
        # The two Components are compared by their attributes
        return [self.plane, self.source_exponents, self.test_exponents] < \
               [other.plane, other.source_exponents, other.test_exponents]

    def __eq__(self, other: Component) -> bool:
        """
        Implements the __eq__ method for the Component class. Two Components are designated as "equal" if the following
        two conditions hold:
        1. They are compatible for addition. That is, all of their attributes, apart from impedance- and wake functions,
        are exactly equal.
        2. The resulting values from evaluating the impedance functions of the two components respectively for 50
        points between 1 and 10000 all need to be close within some given tolerance. The same has to hold for the wake
        function.
        This somewhat approximated numerical approach to the equality comparator aims to compensate for small
        numerical/precision errors accumulated for two Components which have taken different "paths" to what should
        analytically be identical Components.
        :param other: The right hand side of the equality comparator
        :return: True if the two Components have identical attributes and sufficiently close functions, False otherwise
        """
        # First checks if the two Components are compatible for addition, i.e. if they have the same non-function
        # attributes
        if not self.is_compatible(other):
            # If they do not, they are not equal
            return False

        # Creates a numpy array of 50 points and verifies that the evaluations of the functions of the two components
        # for all of these components are sufficiently close. If they are, True is returned, otherwise, False is
        # returned.
        xs = np.linspace(1, 10000, 50)
        return (np.allclose(self.impedance(xs), other.impedance(xs), rtol=REL_TOL, atol=ABS_TOL) and
                np.allclose(self.wake(xs), other.wake(xs), rtol=REL_TOL, atol=ABS_TOL))

    def impedance_to_array(self, rough_points: int, start: float = MIN_FREQ,
                           stop: float = MAX_FREQ,
                           precision_factor: float = FREQ_P_FACTOR) -> Tuple[np.ndarray, np.ndarray]:
        """
        Produces a frequency grid based on the f_rois attribute of the component and evaluates the component's
        impedance function at these frequencies.
        :param rough_points: The total number of data points to be
                             generated for the rough grid, between start
                             and stop.
        :param start: The lowest frequency in the desired frequency grid
        :param stop: The highest frequency in the desired frequency grid
        :param precision_factor: A number indicating the ratio of points
               which should be placed within the regions of interest.
               If =0, the frequency grid will ignore the intervals in f_rois.
               If =1, the points will be distributed 1:1 between the
               rough grid and the fine grid on each roi. In general, =n
               means that there will be n times more points in the fine
               grid of each roi, than in the rough grid.
        :return: A tuple of two numpy arrays with same shape, giving
                 the frequency grid and impedances respectively
        """
        if len(self.f_rois) == 0:
            xs = np.geomspace(start, stop, rough_points)
            return xs, self.impedance(xs)

        # eliminate duplicates
        f_rois_no_dup = set(self.f_rois)

        fine_points_per_roi = int(round(rough_points * precision_factor))

        xs = mix_fine_and_rough_sampling(start, stop, rough_points,
                                         fine_points_per_roi,
                                         list(f_rois_no_dup))

        return xs, self.impedance(xs)

    def wake_to_array(self, rough_points: int, start: float = MIN_TIME,
                      stop: float = MAX_TIME,
                      precision_factor: float = TIME_P_FACTOR) -> Tuple[np.ndarray, np.ndarray]:
        """
        Produces a time grid based on the t_rois attribute of the component and evaluates the component's
        wake function at these time points.
        :param rough_points: The total number of data points to be
                             generated for the rough grid, between start
                             and stop.
        :param start: The lowest time in the desired time grid
        :param stop: The highest time in the desired time grid
        :param precision_factor: A number indicating the ratio of points
               which should be placed within the regions of interest.
               If =0, the frequency grid will ignore the intervals in t_rois.
               If =1, the points will be distributed 1:1 between the
               rough grid and the fine grid on each roi. In general, =n
               means that there will be n times more points in the fine
               grid of each roi, than in the rough grid.
        :return: A tuple of two numpy arrays with same shape, giving the
                 time grid and wakes respectively
        """
        if len(self.t_rois) == 0:
            xs = np.geomspace(start, stop, rough_points)
            return xs, self.wake(xs)

        # eliminate duplicates
        t_rois_no_dup = set(self.t_rois)

        fine_points_per_roi = int(round(rough_points * precision_factor))

        xs = mix_fine_and_rough_sampling(start, stop, rough_points,
                                         fine_points_per_roi,
                                         list(t_rois_no_dup))

        return xs, self.wake(xs)

    def discretize(self, freq_points: int, time_points: int, freq_start: float = MIN_FREQ, freq_stop: float = MAX_FREQ,
                   time_start: float = MIN_TIME, time_stop: float = MAX_TIME,
                   freq_precision_factor: float = FREQ_P_FACTOR,
                   time_precision_factor: float = TIME_P_FACTOR) -> Tuple[
        Tuple[np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray]]:
        """
        Combines the two discretization-functions in order to fully discretize the wake and impedance of the object
        as specified by a number of parameters.
        :param freq_points: The total number of frequency/impedance points
        :param time_points: The total number of time/wake points
        :param freq_start: The lowest frequency in the frequency grid
        :param freq_stop: The highest frequency in the frequency grid
        :param time_start: The lowest time in the time grid
        :param time_stop: The highest time in the time grid
        :param freq_precision_factor: The ratio of points in the fine frequency grid
        (#points in frequency ROIs / rough frequency points)
        :param time_precision_factor: The ratio of points in the fine time grid
        (#points in time ROIs / rough time points)
        :return: A tuple of two tuples, containing the results of impedance_to_array and wake_to_array respectively
        """
        return (self.impedance_to_array(freq_points, freq_start, freq_stop, freq_precision_factor),
                self.wake_to_array(time_points, time_start, time_stop, time_precision_factor))

    def get_shorthand_type(self) -> str:
        """
        :return: A 5-character string indicating the plane as well as source- and test exponents of the component
        """
        return self.plane + "".join(str(x) for x in (self.source_exponents + self.test_exponents))


class ComponentResonator(Component):
    def __init__(self,
                kind: str = None,
                plane: str = None,
                exponents: Tuple[int, int, int, int]| None = None,
                source_exponents: Tuple[int, int] | None = None,
                test_exponents: Tuple[int, int] | None = None,
                r: float = None, q: float = None, f_r: float = None,
                f_roi_level: float = 0.5,
                factor=1.0) -> ComponentResonator:
        """
        Creates a resonator component with the given parameters
        :param plane: the plane the component corresponds to
        :param exponents: four integers corresponding to (source_x, source_y,
        test_x, test_y) aka (a, b, c, d)
        :param r: the shunt impedance of the given component of the resonator
        :param q: the quality factor of the given component of the resonator
        :param f_r: the resonance frequency of the given component of the
        resonator
        :param f_roi_level: fraction of the peak ok the resonator which is
        covered by the ROI. I.e. the roi will cover
        the frequencies for which the resonator impedance is larger than
        f_roi_level*r
        :return: A component object of a resonator, specified by the input
        arguments
        """
        self.r = r
        self.q = q
        self.f_r = f_r
        self.f_roi_level = f_roi_level
        self.factor = factor

        source_exponents, test_exponents, plane = _handle_plane_and_exponents_input(
                                    kind=kind, exponents=exponents,
                                    source_exponents=source_exponents,
                                    test_exponents=test_exponents,
                                    plane=plane)

        # we set impedance and wake to a dummy callable because they will be
        # overridden by methods
        super().__init__(impedance=lambda x: 0, wake=lambda x: 0, plane=plane,
                         source_exponents=source_exponents,
                         test_exponents=test_exponents,
                         name="Resonator")

    def impedance(self, f):
        f = np.atleast_1d(f)
        f_r = self.f_r
        q = self.q
        r = self.r
        factor = self.factor
        plane = self.plane
        if plane == 'z':
            out = factor * r / (1 - 1j * q * (f_r / f - f / f_r))
        else:
            out = factor * (f_r * r) / (f * (1 - 1j * q * (f_r / f - f / f_r)))

        return out


    def wake(self, t):
        t = np.atleast_1d(t)
        f_r = self.f_r
        q = self.q
        r = self.r
        factor = self.factor
        plane = self.plane
        omega_r = 2 * np.pi * f_r
        root_term = np.sqrt(1 - 1 / (4 * q ** 2) + 0J)
        if plane == 'z':
            omega_bar = omega_r * root_term
            alpha = omega_r / (2 * q)
            out = np.zeros_like(t)
            mask = t >= 0
            out[mask] = factor * (omega_r * r * np.exp(-alpha * t[mask]) * (
                   np.cos(omega_bar * t[mask]) -
                   alpha * np.sin(omega_bar * t[mask]) / omega_bar) / q).real
        else:
            omega_bar = omega_r * root_term
            out = np.zeros_like(t)
            mask = t >= 0
            out[mask] = factor * (omega_r * r * np.exp(-omega_r * t[mask] / (2 * q)) *
                   np.sin(omega_r * root_term * t[mask]) /
                   (q * root_term)).real
        return out

    def function_vs_t(self, t, beta0, dt):
        out = self.wake(t)
        isscalar = np.isscalar(t)
        mask_left_edge = np.abs(t) < dt / 2
        # Handle discontinuity at t=0 consistently with beam loading theorem
        out[mask_left_edge] = 0.5 * self.wake(0)
        if isscalar:
            out = out[0]
        return out

    @property
    def f_rois(self):
        if self.q > 1:
            d = self._compute_resonator_f_roi_half_width(
                q=self.q, f_r=self.f_r, f_roi_level=self.f_roi_level)
            return [(self.f_r - d, self.f_r + d)]
        else:
            return []

    @property
    def t_rois(self):
        return []

    @staticmethod
    def _compute_resonator_f_roi_half_width(q: float, f_r: float,
                                            f_roi_level: float = 0.5):
        aux = np.sqrt((1 - f_roi_level) / f_roi_level)

        return (aux + np.sqrt(aux**2 + 4*q**2))*f_r/(2*q) - f_r


class ComponentClassicThickWall(Component):
    def __init__(self,
                 kind: str = None,
                 plane: str = None,
                 exponents: Tuple[int, int, int, int] | None = None,
                 source_exponents: Tuple[int, int] | None = None,
                 test_exponents: Tuple[int, int] | None = None,
                 layer: Layer = None,
                 radius: float = None,
                 resistivity: float = None,
                 factor: float = 1.0,
                 zero_rel_tol: float = 0.01
                 ) -> ComponentClassicThickWall:
        """
        Creates a single component object modeling a resistive wall
        impedance/wake, based on the "classic thick wall formula" (see e.g.
        A. W. Chao, chap. 2 in "Physics of Collective Beams Instabilities in
        High Energy Accelerators", John Wiley and Sons, 1993).
        Only longitudinal and transverse dipolar impedances are supported here.
        :param plane: the plane the component corresponds to
        :param exponents: four integers corresponding to (source_x, source_y,
        test_x, test_y) aka (a, b, c, d)
        :param layer: the chamber material, as a wit Layer object
        :param radius: the chamber radius in m
        :return: A component object
        """

        if (layer is None and resistivity is None):
            raise ValueError(
                "Either a layer object or a resistivity must be provided")
        if layer is not None and resistivity is not None:
            raise ValueError(
                "Both a layer object and a resistivity cannot be provided")

        if radius is None:
            raise ValueError("Radius must be provided")

        self.layer = layer
        self.radius = radius
        self.plane = plane
        self.factor = factor
        self.resistivity = resistivity
        self.zero_rel_tol = zero_rel_tol

        source_exponents, test_exponents, plane = _handle_plane_and_exponents_input(
                                    kind=kind, exponents=exponents,
                                    source_exponents=source_exponents,
                                    test_exponents=test_exponents,
                                    plane=plane)

        # we set impedance and wake to a dummy callable because they will be
        # overridden by methods
        super().__init__(impedance=lambda x: 0, wake=lambda x: 0, plane=plane,
                         source_exponents=source_exponents,
                         test_exponents=test_exponents,
                         name="Classic Thick Wall")

    def impedance(self, f):
        layer = self.layer
        material_magnetic_permeability = mu0
        if layer is not None:
            self._check_layer(layer) # Checks that there are no unsupported layer properties
                                # (e.g. permeability different from vacuum)
            material_resistivity = layer.dc_resistivity
        else:
            material_resistivity = self.resistivity

        radius = self.radius
        plane = self.plane
        factor = self.factor
        exponents = tuple(self.source_exponents + self.test_exponents)

        if plane == 'z' and exponents == (0, 0, 0, 0):
            out = factor * ((1 + np.sign(f)*1j) * material_resistivity
                            / (2* np.pi * radius)
                            / self.delta_skin(f, material_resistivity,
                                              material_magnetic_permeability))
        # Transverse dipolar impedance
        elif ((plane == 'x' and exponents == (1, 0, 0, 0)) or
                (plane == 'y' and exponents == (0, 1, 0, 0))):
            out = factor * ((1 + np.sign(f)*1j) * material_resistivity
                            / (np.pi * radius**3 * (2 * np.pi * f * np.sqrt(eps0 * mu0)))
                            / self.delta_skin(f, material_resistivity,
                                              material_magnetic_permeability))
        else:
            raise ValueError("Resistive wall wake not implemented for "
                  "component {}{}. Set to zero".format(plane, exponents))

        return out

    def wake(self, t, beta0=None):
        layer = self.layer
        if layer is not None:
            self._check_layer(layer) # Checks that there are no unsupported layer properties
                                # (e.g. permeability different from vacuum)
            material_resistivity = layer.dc_resistivity
        else:
            material_resistivity = self.resistivity
        radius = self.radius
        plane = self.plane
        factor = self.factor
        exponents = tuple(self.source_exponents + self.test_exponents)

        beta0 = beta0 if beta0 is not None else 1

        isscalar = np.isscalar(t)
        t = np.atleast_1d(t)
        mask_positive = t > 1e-20
        out = np.zeros_like(t)

        # Longitudinal
        if plane == 'z' and exponents == (0, 0, 0, 0):
            out[mask_positive] = factor * (-1. / (4 * np.pi * radius)
                            * np.sqrt(Z0 * material_resistivity / np.pi / c_light)
                            * 1/(t[mask_positive]**(3/2)))
        # Transverse dipolar
        elif ((plane == 'x' and exponents == (1, 0, 0, 0)) or
                (plane == 'y' and exponents == (0, 1, 0, 0))):
            out[mask_positive] = factor * (
                        1. / (np.pi * radius**3)
                        * np.sqrt(c_light * Z0 * material_resistivity / np.pi)
                        * 1/(t[mask_positive]**(1/2)))
        else:
            raise ValueError("Resistive wall wake not implemented for "
                  "component {}{}. Set to zero".format(plane, exponents))

        if isscalar:
            out = out[0]

        return out

    @staticmethod
    def delta_skin(f, material_resistivity, material_magnetic_permeability):
        return np.sqrt(2 * material_resistivity / (2*np.pi*abs(f) *
                                        material_magnetic_permeability))

    @property
    def f_rois(self):
        return []

    @property
    def t_rois(self):
        return []

    def function_vs_t(self, t, beta0, dt):

        isscalar = np.isscalar(t)
        t = np.atleast_1d(t)

        assert dt > 0
        mask_zero = np.abs(t) < dt * self.zero_rel_tol
        out = np.zeros_like(t)
        out[mask_zero] = self.wake(dt * self.zero_rel_tol, beta0=beta0)
        out[~mask_zero] = self.wake(t[~mask_zero], beta0=beta0)

        if isscalar:
            out = out[0]
        return out

    @staticmethod
    def _check_layer(layer):
        if not isinstance(layer, Layer):
            raise ValueError("Layer must be a wit Layer object")
        if layer.thickness is not None:
            raise ValueError("Layer thickness not supported for "
                             "classic thick wall impedance")
        if layer.re_dielectric_constant != 1.0:
            raise ValueError("Dielectric constant not supported for "
                             "classic thick wall impedance")
        if layer.permeability_relaxation_frequency < np.inf:
            raise ValueError("Permeability relaxation frequency not supported for "
                             "classic thick wall impedance")


class ComponentSingleLayerResistiveWall(Component):
    def __init__(self,
                 kind: str = None,
                 plane: str = None,
                 exponents: Tuple[int, int, int, int] = None,
                 source_exponents: Tuple[int, int] | None = None,
                 test_exponents: Tuple[int, int] | None = None,
                 input_data: Union[FlatIW2DInput, RoundIW2DInput] = None,
                 factor: float = 1.0):
        """
        Creates a single component object modeling a resistive wall impedance,
        based on the single-layer approximated formulas by E. Metral (see e.g.
        Eqs. 13-14 in N. Mounet and E. Metral, IPAC'10, TUPD053,
        https://accelconf.web.cern.ch/IPAC10/papers/tupd053.pdf, and
        Eq. 21 in F. Roncarolo et al, Phys. Rev. ST Accel. Beams 12, 084401,
        2009, https://doi.org/10.1103/PhysRevSTAB.12.084401)
        :param plane: the plane the component corresponds to
        :param exponents: four integers corresponding to (source_x, source_y,
        test_x, test_y) aka (a, b, c, d)
        :param input_data: an IW2D input object (flat or round). If the input
        is of type FlatIW2DInput and symmetric, we apply to the round formula
        the Yokoya factors for an infinitely flat structure (see e.g. K. Yokoya,
        KEK Preprint 92-196 (1993), and Part. Accel. 41 (1993) pp.221-248,
        https://cds.cern.ch/record/248630/files/p221.pdf),
        while for a single plate we use those from A. Burov and V. Danilov,
        PRL 82,11 (1999), https://doi.org/10.1103/PhysRevLett.82.2286. Other
        kinds of asymmetric structure will raise an error.
        If the input is of type RoundIW2DInput, the structure is in principle
        round but the Yokoya factors put in the input will be used.
        :return: A component object
        """
        self.input_data = input_data
        self.plane = plane
        self.factor = factor

        source_exponents, test_exponents, plane = _handle_plane_and_exponents_input(
                                    kind=kind, exponents=exponents,
                                    source_exponents=source_exponents,
                                    test_exponents=test_exponents,
                                    plane=plane)
        factor = self.factor

        if isinstance(input_data, FlatIW2DInput):
            if len(input_data.top_layers) > 1:
                raise NotImplementedError("Input data can have only one layer")
            self.yok_long = 1.
            self.layer = input_data.top_layers[0]
            self.radius = input_data.top_half_gap
            if input_data.top_bottom_symmetry:
                self.yok_dipx = np.pi**2/24.
                self.yok_dipy = np.pi**2/12.
                self.yok_quax = -np.pi**2/24.
                self.yok_quay = np.pi**2/24.
            elif input_data.bottom_half_gap == np.inf:
                self.yok_dipx = 0.25
                self.yok_dipy = 0.25
                self.yok_quax = -0.25
                self.yok_quay = 0.25
            else:
                raise NotImplementedError("For asymmetric structures, only the "
                                          "case of a single plate is "
                                          "implemented; hence the bottom "
                                          "half-gap must be infinite")
        elif isinstance(input_data, RoundIW2DInput):
            self.radius = input_data.inner_layer_radius
            if len(input_data.layers) > 1:
                raise NotImplementedError("Input data can have only one layer")
            self.layer = input_data.layers[0]
            self.yok_long = input_data.yokoya_factors[0]
            self.yok_dipx = input_data.yokoya_factors[1]
            self.yok_dipy = input_data.yokoya_factors[2]
            self.yok_quax = input_data.yokoya_factors[3]
            self.yok_quay = input_data.yokoya_factors[4]
        else:
            raise NotImplementedError("Input of type neither FlatIW2DInput nor "
                                       "RoundIW2DInput cannot be handled")


        # we set impedance and wake to a dummy callable because they will be
        # overridden by methods
        super().__init__(impedance=lambda x: 0, wake=lambda x: 0, plane=plane,
                         source_exponents=source_exponents,
                         test_exponents=test_exponents,
                         name="Single layer resistive wall")

    def impedance(self, f):

        factor = self.factor

        # Longitudinal impedance
        if (self.plane == 'z' and self.source_exponents == (0, 0)
           and self.test_exponents == (0, 0)):
            out = factor * self.yok_long*self._zlong_round_single_layer_approx(
                                    frequencies=f,
                                    gamma=self.input_data.relativistic_gamma,
                                    layer=self.layer,
                                    radius=self.radius,
                                    length=self.input_data.length)
        # Transverse impedances
        elif (self.plane == 'x' and self.source_exponents == (1, 0) and
              self.test_exponents == (0, 0)):
            out = factor * self.yok_dipx * self._zdip_round_single_layer_approx(
                frequencies=f,
                gamma=self.input_data.relativistic_gamma,
                layer=self.layer,
                radius=self.radius,
                length=self.input_data.length)
        elif (self.plane == 'y' and self.source_exponents == (0, 1) and
              self.test_exponents == (0, 0)):
            out = factor * self.yok_dipy * self._zdip_round_single_layer_approx(
                frequencies=f,
                gamma=self.input_data.relativistic_gamma,
                layer=self.layer,
                radius=self.radius,
                length=self.input_data.length)
        elif (self.plane == 'x' and self.source_exponents == (0, 0)
             and self.test_exponents == (1, 0)):
            out = factor * self.yok_quax * self._zdip_round_single_layer_approx(
                frequencies=f,
                gamma=self.input_data.relativistic_gamma,
                layer=self.layer,
                radius=self.radius,
                length=self.input_data.length)
        elif (self.plane == 'y' and self.source_exponents == (0, 0) and
              self.test_exponents == (0, 1)):
            out = factor * self.yok_quay * self._zdip_round_single_layer_approx(
                frequencies=f,
                gamma=self.input_data.relativistic_gamma,
                layer=self.layer,
                radius=self.radius,
                length=self.input_data.length)
        else:
            out = np.zeros_like(f)

        return out

    def wake(self, t):
        raise NotImplementedError("Wake not implemented for single-layer "
                                  "resistive wall impedance")

    @staticmethod
    def _zlong_round_single_layer_approx(frequencies: ArrayLike, gamma: float,
                                         layer: Layer, radius: float,
                                         length: float) -> ArrayLike:
        """
        Function to compute the longitudinal resistive-wall impedance from
        the single-layer, approximated formula for a cylindrical structure,
        by E. Metral (see e.g. Eqs. 13-14 in N. Mounet and E. Metral, IPAC'10,
        TUPD053, https://accelconf.web.cern.ch/IPAC10/papers/tupd053.pdf, and
        Eq. 21 in F. Roncarolo et al, Phys. Rev. ST Accel. Beams 12, 084401,
        2009, https://doi.org/10.1103/PhysRevSTAB.12.084401)
        :param frequencies: the frequencies (array) (in Hz)
        :param gamma: relativistic mass factor
        :param layer: a layer with material properties (only resistivity,
        relaxation time and magnetic susceptibility are taken into account
        at this stage)
        :param radius: the radius of the structure (in m)
        :param length: the total length of the resistive object (in m)
        :return: Zlong, the longitudinal impedance at these frequencies
        """
        beta = np.sqrt(1 - 1 / gamma**2)
        omega = 2 * np.pi * frequencies
        k = omega / (beta * c_light)

        rho = layer.dc_resistivity
        tau = layer.resistivity_relaxation_time
        mu1 = 1 + layer.magnetic_susceptibility
        eps1 = 1 - 1j / (eps0 * rho * omega * (1 + 1j * omega * tau))
        nu = k * np.sqrt(1 - beta**2 * eps1 * mu1)

        coef_long = 1j * omega * mu0 * length / (2 * np.pi * beta**2 * gamma**2)

        x1 = k * radius / gamma
        x1sq = x1**2
        x2 = nu * radius

        zlong = coef_long * (sp.k0(x1) / sp.i0(x1) -
                             1 / (x1sq * (1/2 + eps1 * sp.kve(1, x2)/
                                          (x2 * sp.kve(0, x2)))))

        return zlong

    @staticmethod
    def _zdip_round_single_layer_approx(frequencies: ArrayLike, gamma: float,
                                        layer: Layer, radius: float,
                                        length: float) -> ArrayLike:
        """
        Function to compute the transverse dipolar resistive-wall impedance from
        the single-layer, approximated formula for a cylindrical structure,
        Eqs. 13-14 in N. Mounet and E. Metral, IPAC'10, TUPD053,
        https://accelconf.web.cern.ch/IPAC10/papers/tupd053.pdf, and
        Eq. 21 in F. Roncarolo et al, Phys. Rev. ST Accel. Beams 12, 084401,
        2009, https://doi.org/10.1103/PhysRevSTAB.12.084401)
        :param frequencies: the frequencies (array) (in Hz)
        :param gamma: relativistic mass factor
        :param layer: a layer with material properties (only resistivity,
        relaxation time and magnetic susceptibility are taken into account
        at this stage)
        :param radius: the radius of the structure (in m)
        :param length: the total length of the resistive object (in m)
        :return: Zdip, the transverse dipolar impedance at these frequencies
        """
        beta = np.sqrt(1 - 1 / gamma**2)
        omega = 2 * np.pi * frequencies
        k = omega / (beta * c_light)

        rho = layer.dc_resistivity
        tau = layer.resistivity_relaxation_time
        mu1 = 1 + layer.magnetic_susceptibility
        eps1 = 1 - 1j/(eps0 * rho * omega*(1 + 1j * omega * tau))
        nu = k * np.sqrt(1 - beta**2 * eps1 * mu1)

        coef_dip = 1j * k**2 * Z0 * length/(4. * np.pi * beta * gamma**4)

        x1 = k * radius / gamma
        x1sq = x1**2
        x2 = nu * radius

        zdip = coef_dip * (sp.k1(x1) / sp.i1(x1) +
                           4 * beta**2 * gamma**2 /
                           (x1sq*(2 + x2 * sp.kve(0, x2) /
                                  (mu1 * sp.kve(1, x2)))))

        return zdip


class ComponentTaperSingleLayerRestsistiveWall(Component):
    def __init__(self,
                 kind: str = None,
                 plane: str = None,
                 exponents: Tuple[int, int, int, int] = None,
                 source_exponents: Tuple[int, int] | None = None,
                 test_exponents: Tuple[int, int] | None = None,
                 input_data: Union[FlatIW2DInput, RoundIW2DInput] = None,
                 radius_small: float = None, radius_large: float = None,
                 step_size: float = 1e-3,
                 factor: float = 1.0) -> ComponentTaperSingleLayerRestsistiveWall:
        """
        Creates a single component object modeling a round or flat taper (flatness
        along the horizontal direction, change of half-gap along the vertical one)
        resistive-wall impedance, using the integration of the radius-dependent
        approximated formula for a cylindrical structure (see
        the above functions), over the length of the taper.
        :param plane: the plane the component corresponds to
        :param exponents: four integers corresponding to (source_x, source_y, test_x, test_y) aka (a, b, c, d)
        :param input_data: an IW2D input object (flat or round). If the input
        is of type FlatIW2DInput and symmetric, we apply to the round formula the
        Yokoya factors for an infinitely flat structure (see e.g. K. Yokoya,
        KEK Preprint 92-196 (1993), and Part. Accel. 41 (1993) pp.221-248,
        https://cds.cern.ch/record/248630/files/p221.pdf),
        while for a single plate we use those from A. Burov and V. Danilov,
        PRL 82,11 (1999), https://doi.org/10.1103/PhysRevLett.82.2286. Other
        kinds of asymmetric structure will raise an error.
        If the input is of type RoundIW2DInput, the structure is in principle
        round but the Yokoya factors put in the input will be used.
        Note that the radius or half-gaps in input_data are not used (replaced
        by the scan from radius_small to radius_large, for the integration).
        :param radius_small: the smallest radius of the taper (in m)
        :param radius_large: the largest radius of the taper (in m)
        :param step_size: the step size (in the radial or vertical direction)
        for the integration (in m)
        :return: A component object
        """
        self.input_data = input_data
        self.radius_large = radius_large
        self.radius_small = radius_small
        self.step_size = step_size
        self.plane = plane
        self.factor = factor

        source_exponents, test_exponents, plane = _handle_plane_and_exponents_input(
                                    kind=kind, exponents=exponents,
                                    source_exponents=source_exponents,
                                    test_exponents=test_exponents,
                                    plane=plane)

        if isinstance(input_data, FlatIW2DInput):
            if len(input_data.top_layers) > 1:
                raise NotImplementedError("Input data can have only one layer")
            self.yok_long = 1.
            self.layer = input_data.top_layers[0]
            self.radius = input_data.top_half_gap
            if input_data.top_bottom_symmetry:
                self.yok_dipx = np.pi**2/24.
                self.yok_dipy = np.pi**2/12.
                self.yok_quax = -np.pi**2/24.
                self.yok_quay = np.pi**2/24.
            elif input_data.bottom_half_gap == np.inf:
                self.yok_dipx = 0.25
                self.yok_dipy = 0.25
                self.yok_quax = -0.25
                self.yok_quay = 0.25
            else:
                raise NotImplementedError("For asymmetric structures, only the case of a single plate is implemented; "
                                        "hence the bottom half gap must be infinite")
        elif isinstance(input_data, RoundIW2DInput):
            self.radius = input_data.inner_layer_radius
            if len(input_data.layers) > 1:
                raise NotImplementedError("Input data can have only one layer")
            self.layer = input_data.layers[0]
            self.yok_long = input_data.yokoya_factors[0]
            self.yok_dipx = input_data.yokoya_factors[1]
            self.yok_dipy = input_data.yokoya_factors[2]
            self.yok_quax = input_data.yokoya_factors[3]
            self.yok_quay = input_data.yokoya_factors[4]
        else:
            raise NotImplementedError("Input of type neither FlatIW2DInput nor RoundIW2DInput cannot be handled")

        # we set impedance and wake to a dummy callable because they will be
        # overridden by methods
        super().__init__(impedance=lambda x: 0, wake=lambda x: 0, plane=plane,
                         source_exponents=source_exponents,
                         test_exponents=test_exponents,
                         name="Taper single layer resistive wall")

    def impedance(self, f):

        factor = self.factor
        # Longitudinal impedance
        if (self.plane == 'z' and self.source_exponents == (0, 0)
            and self.test_exponents == (0, 0)):
            out = factor * self.yok_long*self._zlong_round_taper_RW_approx(
                            frequencies=f,
                            gamma=self.input_data.relativistic_gamma,
                            layer=self.layer,
                            radius_small=self.radius_small,
                            radius_large=self.radius_large,
                            length=self.input_data.length,
                            step_size=self.step_size)
        # Transverse impedances
        elif (self.plane == 'x' and self.source_exponents == (1, 0)
              and self.test_exponents == (0, 0)):
            out = factor * self.yok_dipx*self._zdip_round_taper_RW_approx(
                            frequencies=f,
                            gamma=self.input_data.relativistic_gamma,
                            layer=self.layer,
                            radius_small=self.radius_small,
                            radius_large=self.radius_large,
                            length=self.input_data.length,
                            step_size=self.step_size)
        elif (self.plane == 'y' and self.source_exponents == (0, 1)
              and self.test_exponents == (0, 0)):
            out = factor * self.yok_dipy*self._zdip_round_taper_RW_approx(
                            frequencies=f,
                            gamma=self.input_data.relativistic_gamma,
                            layer=self.layer,
                            radius_small=self.radius_small,
                            radius_large=self.radius_large,
                            length=self.input_data.length,
                            step_size=self.step_size)
        elif (self.plane == 'x' and self.source_exponents == (0, 0)
             and self.test_exponents == (1, 0)):
            out = factor * self.yok_quax*self._zdip_round_taper_RW_approx(
                            frequencies=f,
                            gamma=self.input_data.relativistic_gamma,
                            layer=self.layer,
                            radius_small=self.radius_small,
                            radius_large=self.radius_large,
                            length=self.input_data.length,
                            step_size=self.step_size)
        elif (self.plane == 'y' and self.source_exponents == (0, 0)
              and self.test_exponents == (0, 1)):
            out = factor * self.yok_quay*self._zdip_round_taper_RW_approx(
                            frequencies=f,
                            gamma=self.input_data.relativistic_gamma,
                            layer=self.layer,
                            radius_small=self.radius_small,
                            radius_large=self.radius_large,
                            length=self.input_data.length,
                            step_size=self.step_size)
        else:
            out = np.zeros_like(f)

        return out


    def wake(self, t):
        raise NotImplementedError("Wake not implemented for single-layer "
                                  "resistive wall impedance")


    @staticmethod
    def _zlong_round_taper_RW_approx(frequencies: ArrayLike, gamma: float,
                                    layer: Layer, radius_small: float,
                                    radius_large: float, length: float,
                                    step_size: float = 1e-3) -> ArrayLike:
        """
        Function to compute the longitudinal resistive-wall impedance for a
        round taper, integrating the radius-dependent approximated formula
        for a cylindrical structure (see_zlong_round_single_layer_approx above),
        over the length of the taper.
        :param frequencies: the frequencies (array) (in Hz)
        :param gamma: relativistic mass factor
        :param layer: a layer with material properties (only resistivity,
        relaxation time and magnetic susceptibility are taken into account
        at this stage)
        :param radius_small: the smallest radius of the taper (in m)
        :param radius_large: the largest radius of the taper (in m)
        :param length: the total length of the taper (in m)
        :param step_size: the step size (in the radial direction) for the
        integration (in m)
        :return: the longitudinal impedance at these frequencies
        """
        if np.isscalar(frequencies):
            frequencies = np.array(frequencies)
        beta = np.sqrt(1.-1./gamma**2)
        omega = 2*np.pi*frequencies.reshape((-1, 1))
        k = omega/(beta*c_light)

        rho = layer.dc_resistivity
        tau = layer.resistivity_relaxation_time
        mu1 = 1.+layer.magnetic_susceptibility
        eps1 = 1. - 1j/(eps0*rho*omega*(1.+1j*omega*tau))
        nu = k*np.sqrt(1.-beta**2*eps1*mu1)

        coef_long = 1j*omega*mu0/(2.*np.pi*beta**2*gamma**2)

        npts = int(np.floor(abs(radius_large-radius_small)/step_size)+1)
        radii = np.linspace(radius_small, radius_large, npts).reshape((1, -1))
        one_array = np.ones(radii.shape)

        x1 = k.dot(radii)/gamma
        x1sq = x1**2
        x2 = nu.dot(radii)
        zlong = (coef_long.dot(length / float(npts) * one_array) *
                (sp.k0(x1) / sp.i0(x1) -
                 1. / (x1sq * (1. / 2. + eps1.dot(one_array) *
                               sp.kve(1, x2) / (x2 * sp.kve(0, x2)))))
                )

        return trapz(zlong, axis=1)


    @staticmethod
    def _zdip_round_taper_RW_approx(frequencies: ArrayLike, gamma: float,
                                    layer: Layer, radius_small: float,
                                    radius_large: float, length: float,
                                    step_size: float = 1e-3) -> ArrayLike:
        """
        Function to compute the transverse dip. resistive-wall impedance for a
        round taper, integrating the radius-dependent approximated formula
        for a cylindrical structure (see_zdip_round_single_layer_approx above),
        over the length of the taper.
        :param frequencies: the frequencies (array) (in Hz)
        :param gamma: relativistic mass factor
        :param layer: a layer with material properties (only resistivity,
        relaxation time and magnetic susceptibility are taken into account
        at this stage)
        :param radius_small: the smallest radius of the taper (in m)
        :param radius_large: the largest radius of the taper (in m)
        :param length: the total length of the taper (in m)
        :param step_size: the step size (in the radial direction) for the
        integration (in m)
        :return: the transverse dipolar impedance at these frequencies
        """
        if np.isscalar(frequencies):
            frequencies = np.array(frequencies)
        beta = np.sqrt(1.-1./gamma**2)
        omega = 2*np.pi*frequencies.reshape((-1,1))
        k = omega/(beta*c_light)

        rho = layer.dc_resistivity
        tau = layer.resistivity_relaxation_time
        mu1 = 1.+layer.magnetic_susceptibility
        eps1 = 1. - 1j/(eps0*rho*omega*(1.+1j*omega*tau))
        nu = k*np.sqrt(1.-beta**2*eps1*mu1)

        coef_dip = 1j*k**2*Z0/(4.*np.pi*beta*gamma**4)

        npts = int(np.floor(abs(radius_large-radius_small)/step_size)+1)
        radii = np.linspace(radius_small,radius_large,npts).reshape((1,-1))
        one_array = np.ones(radii.shape)

        x1 = k.dot(radii)/gamma
        x1sq = x1**2
        x2 = nu.dot(radii)
        zdip = (
                coef_dip.dot(length / float(npts) * one_array) *
                (sp.k1(x1) / sp.i1(x1) +
                 4 * beta**2 * gamma**2 / (x1sq * (2 + x2 * sp.kve(0, x2) /
                                                   (mu1 * sp.kve(1, x2)))))
            )

        return trapz(zdip, axis=1)


class ComponentInterpolated(Component):
    def __init__(self,
                interpolation_frequencies: ArrayLike = None,
                impedance_input: Optional[Callable] = None,
                interpolation_times: ArrayLike = None,
                wake_input: Optional[Callable] = None,
                kind: str = None,
                plane: str = None,
                source_exponents: Tuple[int, int] = None,
                test_exponents: Tuple[int, int] = None,
                name: str = "Interpolated Component",
                f_rois: Optional[List[Tuple[float, float]]] = None,
                t_rois: Optional[List[Tuple[float, float]]] = None):

        assert ((interpolation_frequencies is not None) ==
                (impedance_input is not None)), ("Either both or none of the "
                "impedance and the interpolation frequencies must be given")

        source_exponents, test_exponents, plane = _handle_plane_and_exponents_input(
                            kind=kind, exponents=None,
                            source_exponents=source_exponents,
                            test_exponents=test_exponents,
                            plane=plane)

        self.interpolation_frequencies = interpolation_frequencies
        self.impedance_input = impedance_input

        assert ((interpolation_times is not None) ==
                (wake_input is not None)), ("Either both or none of the wake "
                "and the interpolation times must be given")

        self.interpolation_times = interpolation_times
        self.wake_input = wake_input

        super().__init__(impedance=lambda x: 0, wake=lambda x: 0, plane=plane,
                       source_exponents=source_exponents,
                       test_exponents=test_exponents,
                       f_rois=f_rois, t_rois=t_rois,
                       name=name)

    def impedance(self, f):
        if self.impedance_input is not None:
            return np.interp(f, self.interpolation_frequencies,
                             self.impedance_input)
        else:
            return np.zeros_like(f)

    def wake(self, t):
        if self.wake_input is not None:
            return np.interp(t, self.interpolation_times, self.wake_input,
                             left=0, right=0 # pad with zeros outside the range
            )
        else:
            return np.zeros_like(t)

    def function_vs_t(self, t, beta0, dt):

        assert dt > 0

        isscalar = np.isscalar(t)
        if isscalar:
            t = np.array([t])

        out = self.wake(t)

        # Handle discontinuity at edges (consistently with beam loading theorem)
        mask_left_edge = np.abs(t - self.interpolation_times[0]) < dt / 2
        out[mask_left_edge] = self.wake_input[0] / 2.
        mask_right_edge = np.abs(t - self.interpolation_times[-1]) < dt / 2
        out[mask_right_edge] = self.wake_input[-1] / 2.

        if isscalar:
            out = out[0]

        return out


def _handle_plane_and_exponents_input(kind, exponents, source_exponents, test_exponents, plane):

    if kind is not None:
        assert exponents is None, (
            "If kind is specified, `exponents` should not be specified.")
        assert source_exponents is None and test_exponents is None, (
            "If kind is specified, `source_exponents` and test_exponents should "
            "not be specified.")
        assert test_exponents is None, (
            "If kind is specified, `test_exponents` should not be specified.")
        assert plane is None, (
            "If kind is specified, `plane` should not be specified.")
        assert kind in KIND_DEFINITIONS, f'Unknown kind {kind}'
        source_exponents, test_exponents, plane = (
            KIND_DEFINITIONS[kind]['source_exponents'],
            KIND_DEFINITIONS[kind]['test_exponents'],
            KIND_DEFINITIONS[kind]['plane'])

    if exponents is not None:
        assert source_exponents is None and test_exponents is None, (
            "If exponents is specified, source_exponents and test_exponents "
            "should not be specified.")
        source_exponents = exponents[0:2]
        test_exponents = exponents[2:4]
    elif source_exponents is not None or test_exponents is not None:
        assert source_exponents is not None and test_exponents is not None, (
            "If source_exponents or test_exponents is specified, both should "
            "be specified.")
        assert exponents is None, (
            "If source_exponents or test_exponents is specified, exponents "
            "should not be specified.")

    return source_exponents, test_exponents, plane


class ComponentIndirectSpaceCharge(Component):
    def __init__(self, kind: str = None, plane: str = None,
                 source_exponents: Tuple[int, int] | None = None,
                 test_exponents: Tuple[int, int] | None = None,
                 gamma: float = None,
                 length: float = None,
                 radius: float = None,
                 stop_crit: float = 1e-14,
                 min_zeta: float = 1e-4,
                 max_iter: int = 10_000,
                 n_step: int = 10,
                 factor: float = 1.0):
        """
        Creates a single component object modeling an indirect space charge
        impedance, based on the formulas by N. Mounet, C. Zannini, E. Dadiani,
        E. Metral and A. Rahemtulla (see
        https://inspirehep.net/files/757991d3651ada7c8b8c98557c30511f).
        :param kind: the kind of impedance (e.g. 'dipolar_x', 'quadrupolar_y')
        :param plane: the plane the component corresponds to (e.g. 'x', 'y'), to
        be specified only if kind is not specified
        :param source_exponents: a tuple of two integers (a, b) corresponding
        to the source exponents (to be specified only if kind is not specified)
        :param test_exponents: a tuple of two integers (c, d) corresponding to
        the test exponents (to be specified only if kind is not specified)
        :param gamma: the relativistic gamma factor
        :param length: the length of the structure (in m)
        :param radius: the radius of the structure (in m)
        :param factor: a factor to multiply the impedance by (e.g. for geometric
        factors)
        """

        source_exponents, test_exponents, plane = _handle_plane_and_exponents_input(
                            kind=kind, exponents=None,
                            source_exponents=source_exponents,
                            test_exponents=test_exponents,
                            plane=plane)

        self.gamma = gamma
        self.length = length
        self.radius = radius
        self.factor = factor

        self.stop_crit = stop_crit
        self.min_zeta = min_zeta
        self.max_iter = max_iter
        self.n_step = n_step

        # we set impedance and wake to a dummy callable because they will be
        # overridden by methods
        super().__init__(impedance=lambda x: 0, wake=lambda x: 0, plane=plane,
                         source_exponents=source_exponents,
                         test_exponents=test_exponents,
                         name="Indirect space charge")

    def _wdip_wake_indirect_space_charge_analytic(
            self,
            zeta: float
            ):
        """
        Function to compute the dipolar indirect space charge wake.
        Since the formula contains an infinite sum we use a stopping
        criterion to truncate the sum when the relative increase of the
        term is below a given threshold, which is chosen to be 1e-4 by
        default. The sum will converge very slowly when zeta approaches
        zero, so we use an approximated formula for small zetas.
        In the paper zeta has opposite sign, but it is not relevant since
        the transverse wake turns out to be an even function.
        """

        scalar_input = np.isscalar(zeta)

        gamma = self.gamma
        length = self.length
        radius = self.radius

        min_zeta = self.min_zeta
        stop_crit = self.stop_crit
        max_iter = self.max_iter
        n_step = self.n_step

        zeta = zeta.copy()
        # the formula has a singularity in z=0 and the convergence of the sum
        # is very slow for small zetas, so we set a minimum value for zeta
        zeta[np.abs(zeta) < min_zeta] = min_zeta
        term_1 = ((np.sign(zeta)*length/
                    (4*np.pi*eps0*gamma**4)*1/zeta**3) +
                    1j*0)

        factor = -1j*np.sign(zeta)*length/(2*np.pi*eps0*gamma*radius**3)
        result = term_1
        # we precompute this factor for performance
        prefact = -gamma*np.abs(zeta)/radius

        term_2 = 0
        increase = 1
        N = 0
        while increase > stop_crit and N<max_iter:
            N_old = N
            N += n_step
            j1 = sp.jn_zeros(1, N)

            term_2 = 0

            for k in range(N_old, N):
                term_2 += (np.exp(j1[k]* prefact) *
                        ((j1[k]**2)  * sp.kv(1, np.sign(zeta)*1j*j1[k])) /
                        (sp.j0(j1[k]) - sp.jn(2, j1[k]))
                )

            increase = np.max(-np.real(factor*term_2)/np.real(result))
            result += factor*term_2

        if N >= max_iter:
            print("Warning: the sum in the indirect space charge wake did not"
                  "converge within the maximum number of iterations. The result"
                  "may be inaccurate.")

        if scalar_input:
            return self.factor*result.real[0]
        else:
            return self.factor*result.real


    def _wlong_wake_indirect_space_charge_analytic(
            self,
            zeta: float,
            stop_crit: float = 1e-14,
            min_zeta: float = 1e-4,
            max_iter: int = 10_000,
            n_step: int = 10
            ):
        """
        Function to compute the longitudinal indirect space charge wake.
        Since the formula contains an infinite sum we use a stopping
        criterion to truncate the sum when the relative increase of the
        term is below a given threshold, which is chosen to be 1e-4 by
        default. The sum will converge very slowly when zeta approaches
        zero, so we use an approximated formula for small zetas.
        In the paper zeta has opposite sign, so we change the its sign within 
        the function.
        """
        gamma = self.gamma
        length = self.length
        radius = self.radius

        scalar_input = np.isscalar(zeta)

        zeta = np.atleast_1d(zeta)

        # here we change the sign of zeta to keep the compatibility with our
        # convention
        zeta = -zeta
        # the formula has a singularity in z=0 and the convergence of the sum
        # is very slow for small zetas, so we set a minimum value for zeta
        zeta[np.abs(zeta) < min_zeta] = min_zeta
        term_1 = -((np.sign(zeta)*length/
                    (4*np.pi*eps0*gamma**2)*1/zeta**2) +
                    1j*0)

        factor = -np.sign(zeta)*length/(2*np.pi*eps0*radius**2)
        result = term_1
        # we precompute this factor for performance
        prefact = -gamma*np.abs(zeta)/radius

        term_2 = 0
        increase = 1
        N = 0
        while increase > stop_crit and N<max_iter:
            N_old = N
            N += n_step
            j0 = sp.jn_zeros(0, N)

            term_2 = 0

            for k in range(N_old, N):
                term_2 += (np.exp(j0[k]* prefact) *
                        (j0[k]  * sp.kv(0, np.sign(zeta)*1j*j0[k])) /
                            sp.j1(j0[k])
                )

            increase = np.max(-np.real(factor*term_2)/np.real(result))
            result += factor*term_2

        if N >= max_iter:
            print("Warning: the sum in the indirect space charge wake did not"
                  "converge within the maximum number of iterations. The result"
                  "may be inaccurate.")

        if scalar_input:
            return self.factor*result.real[0]
        else:
            return self.factor*result.real


    def zdip_impedance(self, freq):
        """
        Function to compute the dipolar indirect space charge impedance.
        """
        scalar_input = np.isscalar(freq)

        gamma = self.gamma
        length = self.length
        radius = self.radius

        beta = np.sqrt(1 - 1 / gamma**2)

        omega = 2*np.pi*freq
        k = omega/(beta*c_light)

        impedance = length*(
            1j*k**2*Z0/(4*np.pi*beta*gamma**4) *
            sp.k1(np.abs(k)*radius/gamma) /
            sp.i1(np.abs(k)*radius/gamma))

        if scalar_input:
            return self.factor*impedance.real[0]
        else:
            return self.factor*impedance

    def zlong_impedance(self, freq):
        """
        Function to compute the longitudinal indirect space charge impedance.
        """
        scalar_input = np.isscalar(freq)
        gamma = self.gamma
        length = self.length
        radius = self.radius

        beta = np.sqrt(1 - 1 / gamma**2)

        omega = 2*np.pi*freq
        k = omega/(beta*c_light)

        impedance = (1j*omega*mu0*length/(2*np.pi*beta**2*gamma**2) *
                     sp.k0(np.abs(k)*radius/gamma) /
                     sp.i0(np.abs(k)*radius/gamma))

        if scalar_input:
            return self.factor*impedance.real[0]
        else:
            return self.factor*impedance


    def impedance(self, f):
        if self.plane == 'x' and self.source_exponents == (1, 0) and self.test_exponents == (0, 0):
            return self.zdip_impedance(f)
        elif self.plane == 'y' and self.source_exponents == (0, 1) and self.test_exponents == (0, 0):
            return self.zdip_impedance(f)
        elif self.plane == 'z' and self.source_exponents == (0, 0) and self.test_exponents == (0, 0):
            return self.zlong_impedance(f)
        else:
            return np.zeros_like(f)


    def wake(self, t):
        if self.plane == 'x' and self.source_exponents == (1, 0) and self.test_exponents == (0, 0):
            return self._wdip_wake_indirect_space_charge_analytic(t)
        elif self.plane == 'y' and self.source_exponents == (0, 1) and self.test_exponents == (0, 0):
            return self._wdip_wake_indirect_space_charge_analytic(t)
        elif self.plane == 'z' and self.source_exponents == (0, 0) and self.test_exponents == (0, 0):
            return self._wlong_wake_indirect_space_charge_analytic(t)
        else:
            return np.zeros_like(t)


    def function_vs_t(self, t, beta0, dt):
        out = self.function_vs_zeta(-t*beta0*c_light, beta0, dt)
        return out


    def function_vs_zeta(self, zeta, beta0, dzeta):
        out = self.wake(zeta)
        return out
