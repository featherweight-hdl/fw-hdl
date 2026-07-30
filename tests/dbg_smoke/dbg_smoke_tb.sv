// D-0 smoke: the static half of the observable-events facility.
//
// What this test is really for: the whole design rests on ONE unverified
// language claim -- that a function/block-scope `static` with an initializer is
// elaborated exactly once, before time 0, wherever it is written. If that is
// false, site ids are neither stable nor free and the emit macros need a
// per-hit registration branch. So the checks below are about the IDIOM, not
// about a feature:
//
//   1. one descriptor per SITE, not per activation and not per instance;
//   2. ids stable across calls, instances, and class specializations;
//   3. the catalog is COMPLETE AT TIME 0 -- including a site whose code never
//      runs (§9's artifact describes the image, not the run);
//   4. the same source compiles with the facility compiled out (`FW_TRACE_OFF`).
module dbg_smoke_tb;
    import fw_hdl_pkg::*;
    `include "dbg/fw_dbg_macros.svh"

    int errors = 0;

    function automatic void chk(bit cond, string msg);
        if (!cond) begin $display("FAIL: %s", msg); errors++; end
    endfunction

`ifdef FW_TRACE_OFF
    // Compiled out: there are no sites to check. The point of building this
    // configuration is that the source above and below still compiles.
    initial begin
        $display("[dbg_smoke] PASS (FW_TRACE_OFF: facility compiled out)");
        $finish;
    end
`else

    // --- a site in a module-scope function ---------------------------------
    function automatic int unsigned f_site();
        `fw_dbg_site_decl(SID_F, "smoke.f", FW_DBG_NOTICE, FW_L_VITAL)
        return SID_F;
    endfunction

    // --- a site in a function that is REFERENCED but never REACHED ----------
    // Guarded by a variable the elaborator cannot fold, so the function is not
    // eliminated; the call never happens. Its site must be catalogued anyway.
    bit never = 0;
    function automatic int unsigned f_never();
        `fw_dbg_site_decl(SID_N, "smoke.never", FW_DBG_NOTICE, FW_L_TRACE)
        return SID_N;
    endfunction

    // --- sites in a class: a method, and a block inside a task --------------
    class thing;
        int tag;
        function new(int t); tag = t; endfunction

        function int unsigned m_site();
            `fw_dbg_site_decl(SID_M, "smoke.m", FW_DBG_STATE, FW_L_DETAIL)
            return SID_M;
        endfunction

        task t_site(output int unsigned id);
            begin
                `fw_dbg_site_decl(SID_T, "smoke.t", FW_DBG_OP, FW_L_OP)
                id = SID_T;
            end
        endtask
    endclass

    // --- a site in a PARAMETERIZED class ------------------------------------
    // One site per specialization is the wanted behavior: the field schema of
    // fw_reg #(T) differs per T, so its sites must too.
    class boxed #(type T = int);
        function int unsigned p_site();
            `fw_dbg_site_decl(SID_P, "smoke.p", FW_DBG_STATE, FW_L_DETAIL)
            return SID_P;
        endfunction
    endclass

    initial begin
        automatic int unsigned n_at_time_0 = fw_dbg_catalog::num_sites();
        automatic thing a = new(1);
        automatic thing b = new(2);
        automatic boxed #(int)      pi = new();
        automatic boxed #(bit[7:0]) pb = new();
        automatic int unsigned ta, tb;
        automatic fw_dbg_site  s;

        // ===== 3. the catalog is complete before any of this code ran =======
        chk(n_at_time_0 >= 6, $sformatf(
            "catalog populated before time 0 (saw %0d sites)", n_at_time_0));
        chk(fw_dbg_catalog::find("smoke.never") != null,
            "a site whose code never runs is still catalogued");
        if (never) void'(f_never());   // keep f_never reachable; never taken

        // ===== 1/2. one descriptor per site; ids stable and distinct ========
        chk(f_site() != FW_DBG_NO_SITE, "site id is non-zero");
        chk(f_site() == f_site(),       "id stable across calls");
        chk(a.m_site() == b.m_site(),   "id shared across INSTANCES");
        a.t_site(ta);  b.t_site(tb);
        chk(ta == tb,                   "id shared across instances (block scope)");
        chk(f_site() != a.m_site() && f_site() != ta && a.m_site() != ta,
                                        "distinct sites get distinct ids");
        chk(pi.p_site() != pb.p_site(),
            "a parameterized class gets one site per SPECIALIZATION");

        // registering nothing new: calling every site again must not grow it
        chk(fw_dbg_catalog::num_sites() == n_at_time_0,
            "no site is registered at run time");

        // ===== site metadata round-trips ====================================
        s = fw_dbg_catalog::site(a.m_site());
        chk(s != null,                       "site() resolves a live id");
        if (s != null) begin
            chk(s.name()  == "smoke.m",      "site name");
            chk(s.kind()  == FW_DBG_STATE,   "site kind");
            chk(s.level() == FW_L_DETAIL,    "site level");
            chk(s.line()  != 0,              "site line recorded");
            chk(s.file()  != "",             "site file recorded");
        end
        chk(fw_dbg_catalog::site(FW_DBG_NO_SITE) == null, "site(0) is null");
        chk(fw_dbg_catalog::site(n_at_time_0 + 100) == null, "site(oob) is null");

        // ===== field schema + record rendering ==============================
        begin
            automatic fw_dbg_site fs = fw_dbg_catalog::site(f_site());
            automatic fw_dbg_rec  r  = new();
            fs.add_field("adr");
            fs.add_field("len");
            chk(fs.field_count() == 2,        "schema records two fields");
            chk(fs.field_name(0) == "adr",    "schema is positional");
            chk(fs.field_name(9) == "?",      "out-of-range field name is safe");

            r.site_id = f_site();
            r.kind    = FW_DBG_NOTICE;
            r.stamp   = 42;
            r.push_field(64'h8000_0100);
            r.push_field(8);
            chk(r.to_str().len() > 0,         "record renders");
            $display("  rendered: %s", r.to_str());

            begin
                automatic fw_dbg_rec c = r.copy();
                chk(c.fields.size() == 2 && c.fields[1] == 8, "copy carries payload");
                c.push_field(1);
                chk(r.fields.size() == 2,     "copy is deep enough to be independent");
            end
        end

        if (errors == 0) $display("[dbg_smoke] PASS (%0d sites catalogued)",
                                  fw_dbg_catalog::num_sites());
        else begin
            $display("[dbg_smoke] FAIL (%0d errors)", errors);
            $fatal(1, "[dbg_smoke] FAIL");
        end
        $finish;
    end
`endif /* FW_TRACE_OFF */

endmodule
