
class spl_reqrsp_if #(type Treq, type Trsp);
    pure virtual task call(input Treq in, output Trsp out);
endclass
