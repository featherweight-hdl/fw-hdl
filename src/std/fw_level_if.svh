// A level: a value that is always there, with no handshake. get() returns the
// current value; a reader never waits and may see the same value many times or
// miss one. In RTL it is a data pin only. Reading a level gives up the Kahn
// guarantee for anything that depends on it (fw_channel.svh): use it for
// configuration and status, not for a stream.
interface class fw_level_if #(type T);
    pure virtual function T get();
endclass

// The writing side of a level: set(t) makes t the current value.
interface class fw_level_set_if #(type T);
    pure virtual function void set(input T t);
endclass
