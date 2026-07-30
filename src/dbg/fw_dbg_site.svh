
// A *site* is the STATIC half of an event: everything that is a property of the
// code rather than of the activation. One descriptor per source location, shared
// by every instance and every activation that reaches it.
//
// This is the load-bearing separation of the whole facility (companion doc §3):
// the runtime record carries an id and values; the NAMES -- of the site and of
// each payload field -- live here, are built once before time 0, and are emitted
// as a machine-readable artifact (§9). No `sformatf` on any hot path, ever.
//
// Field schema: positional. A record's fields[i] is named by field_name(i). A
// site's schema is declared once, at registration; the emitter pushes values in
// the same order. A decoder joins the two.
class fw_dbg_site;
    protected int unsigned   m_id;
    protected string         m_name;
    protected fw_dbg_kind_e  m_kind;
    protected fw_dbg_level_e m_level;
    protected string         m_file;
    protected int            m_line;
    protected string         m_fields[$];
    protected fw_dbg_ftype_t m_field_type[$];  // width + signedness + radix, per field

    function new(int unsigned      id,
                 string            name,
                 fw_dbg_kind_e     kind,
                 fw_dbg_level_e    level,
                 string            file = "",
                 int               line = 0);
        m_id    = id;
        m_name  = name;
        m_kind  = kind;
        m_level = level;
        m_file  = file;
        m_line  = line;
    endfunction

    function int unsigned   id();     return m_id;    endfunction
    function string         name();   return m_name;  endfunction
    function fw_dbg_kind_e  kind();   return m_kind;  endfunction
    function fw_dbg_level_e level();  return m_level; endfunction
    function string         file();   return m_file;  endfunction
    function int            line();   return m_line;  endfunction

    // --- field schema --------------------------------------------------------
    // Declared at registration (preferred) or completed on the first emit. Both
    // are pre-steady-state: a site's schema never changes once its first record
    // has been produced, which is what lets a decoder trust it.
    function void add_field(string nm, fw_dbg_ftype_t t = FW_T_none);
        m_fields.push_back(nm);
        m_field_type.push_back(t);
    endfunction

    // The field's DECODE CONTRACT: how wide it was at the source and whether it
    // is signed. Values travel as `longint`, so a stored -1 is 64 ones and
    // nothing in the record says whether that means -1, 0xff or 0xffffffff.
    // This is where that is written down -- once, here, rather than per record.
    function fw_dbg_ftype_t field_type(int i);
        return (i >= 0 && i < m_field_type.size()) ? m_field_type[i] : FW_T_none;
    endfunction

    // Should field i be rendered in hex? A hint only -- it never affects the
    // value, just whether a human can read it. Register data in decimal is
    // technically complete and practically useless.
    function bit field_hex(int i);
        return (i >= 0 && i < m_field_type.size()) ? m_field_type[i].is_hex : 1'b0;
    endfunction

    function int    field_count();      return m_fields.size(); endfunction
    function string field_name(int i);
        return (i >= 0 && i < m_fields.size()) ? m_fields[i] : "?";
    endfunction

    // Human-readable one-liner (catalog dump, text sink header, error messages).
    function string to_str();
        return $sformatf("#%0d %s [%s L%0d] %s:%0d",
                         m_id, m_name, m_kind.name(), int'(m_level), m_file, m_line);
    endfunction

    // The schema as a decoder would consume it: `name:type` per field. Built
    // only by a catalog dump or a sink -- never on an emit path.
    function string schema_str();
        string b = "";
        foreach (m_fields[i]) begin
            b = {b, i == 0 ? "" : ",", m_fields[i], ":",
                 fw_dbg_ftype_str(field_type(i))};
        end
        return b;
    endfunction
endclass
