# Usage: vivado -mode batch -source run.tcl -tclargs <test.sv>
set f [lindex $argv 0]
set name [file rootname [file tail $f]]
read_verilog -sv $f
if {[catch {synth_design -top top -part xc7a35tcpg236-1 -flatten_hierarchy full} err]} {
  puts "RESULT $name SYNTH_FAILED"
  exit 1
}
report_utilization -file out/$name.util.rpt
write_verilog -force -mode funcsim out/$name.funcsim.v
puts "RESULT $name SYNTH_OK"
