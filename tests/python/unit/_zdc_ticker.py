"""A @zdc free-running counter — exercises the every-cycle ``cycles(1)`` idiom
(a pure 1-cycle boundary, not a multi-cycle wait)."""
import zuspec.dataclasses as zdc


@zdc.dataclass
class ticker(zdc.Component):
    clock : zdc.bit = zdc.input()
    reset : zdc.bit = zdc.input()
    count : zdc.u8  = zdc.output(reset=0)

    @zdc.sync(clock=lambda s: s.clock, reset=lambda s: s.reset)
    async def run(self):
        while True:
            self.count = self.count + 1
            await zdc.cycles(1)
