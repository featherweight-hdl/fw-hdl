"""F4 canary: gcd_canary_pkg.sv in zuspec-dataclasses, statement for statement."""
import zuspec.dataclasses as zdc


@zdc.dataclass
class Gcd(zdc.Component):

    def gcd_euclidean(self, a: zdc.u8, b: zdc.u8) -> zdc.u8:
        i: zdc.i32 = 0
        while i < 16:
            if b == 0:
                pass
            else:
                r: zdc.u8 = a % b
                a = b
                b = r
            i = i + 1
        return a

    def gcd_euclidean8(self, a: zdc.u8, b: zdc.u8) -> zdc.u8:
        return self.gcd_euclidean(a, b)
