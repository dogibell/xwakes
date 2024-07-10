from typing import Tuple

from .basewake import BaseWake, _handle_kind
from .wit import ComponentClassicThickWall


class WakeThickResistiveWall(BaseWake):

    def __init__(self, kind: str = None,
                plane: str = None,
                source_exponents: Tuple[int, int] | None = None,
                test_exponents: Tuple[int, int] | None = None,
                radius: float = None,
                resistivity: float = None):

        if kind is not None:

            kind = _handle_kind(kind)

            components = []
            for kk in kind.keys():
                ff = kind[kk]
                if ff == 0: # if the factor is zero we skip the component
                    continue
                cc = ComponentClassicThickWall(
                        radius=radius, resistivity=resistivity,
                        kind=kk,
                        factor=ff, plane=plane)
                components.append(cc)
        else:
            cc = ComponentClassicThickWall(
                        radius=radius, resistivity=resistivity,
                        plane=plane, source_exponents=source_exponents,
                        test_exponents=test_exponents,
                        factor=ff)
            components = [cc]

        self.components = components
        self.kind = kind