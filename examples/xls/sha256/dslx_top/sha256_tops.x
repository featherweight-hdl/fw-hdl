// The DSLX side of E8's comparison: NOT an upstream file.
//
// sha256 returns Digest, a tuple of eight u32; the SV port returns a packed
// struct of the same eight fields. To compare them, this flattens the tuple to
// bits[256], first element most significant, as the struct is laid out. The
// function itself comes from orig/, unmodified.
import xls.examples.sha256;

pub fn sha256_flat(message: bits[512]) -> bits[256] {
    let (d0, d1, d2, d3, d4, d5, d6, d7) = sha256::sha256(message);
    d0 ++ d1 ++ d2 ++ d3 ++ d4 ++ d5 ++ d6 ++ d7
}
