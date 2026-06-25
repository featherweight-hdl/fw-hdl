"""A zuspec-dataclasses (@zdc) blinky — the *second* front end for the
multi-language lowering proof (must be a real module: DataModelFactory uses
inspect.getsource)."""
import zuspec.dataclasses as zdc


@zdc.dataclass
class blinky(zdc.Component):
    clock : zdc.bit = zdc.input()
    reset : zdc.bit = zdc.input()
    led   : zdc.bit = zdc.output(reset=0)

    @zdc.sync(clock=lambda s: s.clock, reset=lambda s: s.reset)
    async def run(self):
        while True:
            await zdc.cycles(100)
            self.led = ~self.led
