// The component factory: create a child by the type it is meant to be, and
// let rules (fw_view_ctx.svh) pick the class that realizes it.
//
//   class q extends fw_component;
//       `fw_component_utils(q)
//       ...
//   endclass
//
//   // in a parent's build():
//   m_q = q::type_id::create("m_q", this);
//
// A class with a parameter object uses `fw_component_param_utils(T) and
// `T::type_id::create(name, this, params)`; its param_t must extend fw_params,
// so a substitute can be handed the object (and must accept it: create stops
// with both class names when it does not). An abstract (virtual) class uses
// `fw_component_abstract_utils(T)`: it can be created only when a rule picks a
// realization. Creating with `new(...)` still works; nothing can substitute
// for a child created that way.
//
// Registration happens when a class's type_id is first used, which in a
// simulator is time 0 (its static `m_inst`). Names are the class names as
// written, in one namespace.

typedef class fw_component;
typedef class fw_view_ctx;
typedef class fw_view_rule;

// The base of every parameter object a substitutable component takes.
class fw_params;
endclass

virtual class fw_component_proxy;
    pure virtual function string type_name();
    pure virtual function fw_component create_obj(string name, fw_component parent,
                                                  fw_params p);
endclass

class fw_factory;
    protected static fw_component_proxy m_types[string];
    protected static string             m_views[string];     // "tag|base" -> realization

    static function void register(fw_component_proxy p);
        m_types[p.type_name()] = p;
    endfunction

    static function bit is_registered(string name);
        return m_types.exists(name);
    endfunction

    // Register `real_t` as `base`'s realization under `tag`.
    static function bit add_view(string tag, fw_component_proxy base, fw_component_proxy real_t);
        m_views[{tag, "|", base.type_name()}] = real_t.type_name();
        return 1;
    endfunction

    static function string view_of(string tag, string base);
        string k = {tag, "|", base};
        return m_views.exists(k) ? m_views[k] : "";
    endfunction

    // The path of `name` under `parent`, below the root.
    static function string path_of(string name, fw_component parent);
        string full;
        int dot;
        if (parent == null) return name;
        full = {parent.get_full_name(), ".", name};
        dot = -1;
        for (int i = 0; i < full.len(); i++) begin
            if (full[i] == ".") begin
                dot = i;
                break;
            end
        end
        return full.substr(dot + 1, full.len() - 1);
    endfunction

    // Create `base` (or what the rules pick) as `name` under `parent`.
    static function fw_component create(string base, string name, fw_component parent,
                                        fw_params p);
        fw_view_ctx  ctx = (parent != null) ? parent.view_ctx() : fw_view_ctx::global();
        string       path = path_of(name, parent);
        fw_view_rule why;
        string       t = ctx.resolve(base, path, why);
        fw_component c;
        if (!m_types.exists(t))
            $fatal(1, "fw_factory: %s (for %s at %s) is not registered: give it %s and use %s::type_id",
                   t, base, path, "`fw_component_utils", t);
        c = m_types[t].create_obj(name, parent, p);
        c.m_create_type = base;
        c.m_create_origin = (why != null) ? why.origin : "";
        return c;
    endfunction
endclass

// A class constructed as new(name, parent).
class fw_component_registry #(type T = fw_component, string TN = "") extends fw_component_proxy;
    typedef fw_component_registry #(T, TN) this_t;
    static this_t m_inst = get();

    static function this_t get();
        if (m_inst == null) begin
            m_inst = new;
            fw_factory::register(m_inst);
        end
        return m_inst;
    endfunction

    virtual function string type_name();
        return TN;
    endfunction

    virtual function fw_component create_obj(string name, fw_component parent, fw_params p);
        T o;
        if (p != null)
            $fatal(1, "fw_factory: %s takes no parameter object, but %s was created with one",
                   TN, name);
        o = new(name, parent);
        return o;
    endfunction

    static function T create(string name, fw_component parent, fw_params p = null);
        fw_component c;
        T o;
        void'(get());
        c = fw_factory::create(TN, name, parent, p);
        if (!$cast(o, c))
            $fatal(1, "fw_factory: %s was picked for %s, but is not a %s", c.m_create_type,
                   name, TN);
        return o;
    endfunction
endclass

// A class constructed as new(name, parent, params), params a T::param_t.
class fw_component_param_registry #(type T = fw_component, string TN = "")
        extends fw_component_proxy;
    typedef fw_component_param_registry #(T, TN) this_t;
    static this_t m_inst = get();

    static function this_t get();
        if (m_inst == null) begin
            m_inst = new;
            fw_factory::register(m_inst);
        end
        return m_inst;
    endfunction

    virtual function string type_name();
        return TN;
    endfunction

    virtual function fw_component create_obj(string name, fw_component parent, fw_params p);
        T o;
        T::param_t tp;
        if (p != null && !$cast(tp, p))
            $fatal(1, "fw_factory: %s's parameter object does not fit %s::param_t", name, TN);
        o = new(name, parent, tp);
        return o;
    endfunction

    static function T create(string name, fw_component parent, fw_params p = null);
        fw_component c;
        T o;
        void'(get());
        c = fw_factory::create(TN, name, parent, p);
        if (!$cast(o, c))
            $fatal(1, "fw_factory: %s was picked for %s, but is not a %s", c.m_create_type,
                   name, TN);
        return o;
    endfunction
endclass

// An abstract class: never constructed itself, only through a realization.
class fw_abstract_registry #(type T = fw_component, string TN = "") extends fw_component_proxy;
    typedef fw_abstract_registry #(T, TN) this_t;
    static this_t m_inst = get();

    static function this_t get();
        if (m_inst == null) begin
            m_inst = new;
            fw_factory::register(m_inst);
        end
        return m_inst;
    endfunction

    virtual function string type_name();
        return TN;
    endfunction

    virtual function fw_component create_obj(string name, fw_component parent, fw_params p);
        $fatal(1, "fw_factory: %s is abstract and no rule picks a realization for %s", TN, name);
        return null;
    endfunction

    static function T create(string name, fw_component parent, fw_params p = null);
        fw_component c;
        T o;
        void'(get());
        c = fw_factory::create(TN, name, parent, p);
        if (!$cast(o, c))
            $fatal(1, "fw_factory: %s was picked for %s, but is not a %s", c.m_create_type,
                   name, TN);
        return o;
    endfunction
endclass
