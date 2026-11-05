// Views: which class realizes each component, chosen by rules rather than by
// editing the code that builds it.
//
// A component created through the factory (`T::type_id::create(name, this)`,
// fw_factory.svh) is created as T unless a rule picks a substitute:
//
//   type  every T becomes S                  ctx.set_type_override(T::type_id::get(),
//                                                                  S::type_id::get());
//   inst  T at paths matching a glob is S    ctx.set_inst_override("sub.q*", ...);
//   view  T becomes its realization          ctx.set_view("rtl");
//         registered under a tag             (`fw_view(rtl, S, T) in class S)
//
// Each component holds a context: a copy of its parent's, taken when its
// do_build() starts, so a rule added in build() applies to the children that
// component creates after adding it, and to their subtrees, and nowhere else.
// The root's context is a copy of fw_view_ctx::global(), where a testbench (or
// the knob package's fw_knob_views()) puts design-wide rules before start().
//
// Paths are below the root: `q`, `sub.q[2]`. Globs use `*` and `?`.
//
// Resolution tries knob rules (origin "knob:...") before rules from source,
// and within each the most recently added first; the first that matches wins,
// and its substitute is resolved again (chains, up to 8).

class fw_view_rule;
    string kind;        // type | inst | view
    string base;        // the created type's name (type, inst)
    string sub;         // the substitute's name (type, inst)
    string glob;        // inst, view
    string tag;         // view
    string origin;      // where the rule came from, for reports

    function bit is_knob();
        return origin.len() >= 5 && origin.substr(0, 4) == "knob:";
    endfunction
endclass

class fw_view_ctx;
    fw_view_rule m_rules[$];
    protected static fw_view_ctx m_global;

    // The rules every root starts from.
    static function fw_view_ctx global();
        if (m_global == null) m_global = new;
        return m_global;
    endfunction

    function fw_view_ctx copy();
        fw_view_ctx c = new;
        c.m_rules = m_rules;
        return c;
    endfunction

    function void set_type_override(fw_component_proxy base, fw_component_proxy sub,
                                    string origin = "");
        add("type", base.type_name(), sub.type_name(), "*", "", origin);
    endfunction

    function void set_type_override_by_name(string base, string sub, string origin = "");
        add("type", base, sub, "*", "", origin);
    endfunction

    function void set_inst_override(string glob, fw_component_proxy base,
                                    fw_component_proxy sub, string origin = "");
        add("inst", base.type_name(), sub.type_name(), glob, "", origin);
    endfunction

    function void set_inst_override_by_name(string glob, string base, string sub,
                                            string origin = "");
        add("inst", base, sub, glob, "", origin);
    endfunction

    // Every component under the glob whose class has a realization registered
    // under `tag` becomes that realization.
    function void set_view(string tag, string glob = "*", string origin = "");
        add("view", "", "", glob, tag, origin);
    endfunction

    protected function void add(string kind, string base, string sub, string glob,
                                string tag, string origin);
        fw_view_rule r = new;
        r.kind = kind;
        r.base = base;
        r.sub = sub;
        r.glob = glob;
        r.tag = tag;
        r.origin = origin;
        m_rules.push_back(r);
    endfunction

    // The rule that applies to creating `base` at `path`, or null.
    function fw_view_rule match(string base, string path);
        for (int pass = 0; pass < 2; pass++) begin
            for (int i = m_rules.size() - 1; i >= 0; i--) begin
                fw_view_rule r = m_rules[i];
                if (r.is_knob() != (pass == 0)) continue;
                if (r.kind == "type" && r.base == base) return r;
                if (r.kind == "inst" && r.base == base && glob_match(r.glob, path)) return r;
                if (r.kind == "view" && glob_match(r.glob, path)
                        && fw_factory::view_of(r.tag, base) != "") return r;
            end
        end
        return null;
    endfunction

    // The class to create for `base` at `path`; `why` is the last rule applied
    // (null when none applies).
    function string resolve(string base, string path, output fw_view_rule why);
        string t = base;
        why = null;
        for (int depth = 0; depth < 8; depth++) begin
            fw_view_rule r = match(t, path);
            string next;
            if (r == null) return t;
            next = (r.kind == "view") ? fw_factory::view_of(r.tag, t) : r.sub;
            if (next == t) return t;
            why = r;
            t = next;
        end
        $fatal(1, "fw_view_ctx: overrides of %s at %s do not settle after 8 steps", base, path);
        return t;
    endfunction

    // `*` matches any run of characters (dots included), `?` any one.
    static function bit glob_match(string pat, string s);
        int p = 0, i = 0, star = -1, mark = 0;
        while (i < s.len()) begin
            if (p < pat.len() && (pat[p] == "?" || pat[p] == s[i])) begin
                p++;
                i++;
            end else if (p < pat.len() && pat[p] == "*") begin
                star = p;
                mark = i;
                p++;
            end else if (star >= 0) begin
                p = star + 1;
                mark++;
                i = mark;
            end else begin
                return 0;
            end
        end
        while (p < pat.len() && pat[p] == "*") p++;
        return p == pat.len();
    endfunction
endclass
