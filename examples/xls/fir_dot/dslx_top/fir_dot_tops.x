// The DSLX side of E6's comparison: NOT an upstream file.
//
// fir_filter_fixed and dot_product_fixed are parametric, so neither can be an
// IR top. These are concrete wrappers at the sizes upstream's tests use; the
// functions themselves come from orig/, unmodified.
import xls.examples.dot_product;
import xls.examples.fir_filter;

pub fn fir_filter_fixed_4_6(samples: s32[6], coefficients: s32[4]) -> s32[3] {
    fir_filter::fir_filter_fixed(samples, coefficients)
}

pub fn dot_product_fixed_32_4(a: s32[4], b: s32[4]) -> s32 {
    dot_product::dot_product_fixed<u32:32, u32:4>(a, b)
}

pub fn dot_product_fixed_8_2(a: s8[2], b: s8[2]) -> s8 {
    dot_product::dot_product_fixed<u32:8, u32:2>(a, b)
}
