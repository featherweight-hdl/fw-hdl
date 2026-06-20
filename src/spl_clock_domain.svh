
typedef class spl_component;

class spl_clock_domain extends spl_component;
    spi_clock_domain        parent;

    task tick();
    endtask
endclass

