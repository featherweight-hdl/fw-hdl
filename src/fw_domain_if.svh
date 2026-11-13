// The common shape of a DOMAIN (docs/reference/clocking.md, "Domains").
//
// A domain is an ambient property of where a component sits: the clock it
// ticks on, the reset that holds it. Each kind has its own API (extending
// fw_domain_if), a component port that is inherited from the parent
// (fw_domain_port), a root bridge from pins, and derived domains built from
// other domains. This file holds what every kind shares: the kind and relation
// enums, the base API, and the kind-free face of a domain port.
typedef enum { FW_DOMAIN_CLOCK, FW_DOMAIN_RESET } fw_domain_kind_e;   // FW_DOMAIN_POWER later
typedef enum { FW_DOMAIN_SAME, FW_DOMAIN_RELATED, FW_DOMAIN_UNRELATED } fw_domain_rel_e;

// What every domain answers, whatever its kind. The source graph (domain_src)
// is the DOMAIN tree -- a derived domain's sources up to the roots -- not the
// component tree. fw_domains::relate() compares two domains through it.
interface class fw_domain_if;
    pure virtual function fw_domain_kind_e domain_kind();
    // Full path of the domain object (an export's full name).
    pure virtual function string           domain_name();
    // Number of sources; 0 for a root domain (one bridged from pins).
    pure virtual function int              domain_nsrc();
    pure virtual function fw_domain_if     domain_src(int i);
    // The domain this one behaves as: itself, or for a pass-through (a
    // divide-by-1 clock domain, a one-source combine) its source's
    // domain_equiv().
    pure virtual function fw_domain_if     domain_equiv();
endclass

// The kind-free face of a domain port (fw_domain_port #(T, K)), so code that
// handles "any domain port" -- the crossing check, fw_endpoint::set_domain --
// needs no per-kind type.
interface class fw_domain_ref;
    pure virtual function fw_domain_kind_e ref_kind();
    // The bound domain, or null while unbound.
    pure virtual function fw_domain_if     ref_domain();
    // Full path of the port (for reports).
    pure virtual function string           ref_name();
endclass
