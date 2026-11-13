"""The parameter pages built from the catalogue: patient and starting material, process, final product."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import monitor as M
from .. import stats as S
from ..monitor_plots import family_figure, mini_trend_figure, oos_type_figure
from ..plots import p_chart_figure
from . import common as C

PATIENT_TYPES = ("Starting material and patient",)
PATIENT_SOURCES = ("Patient / starting material",)
PATIENT_DAYS = ("Apheresis",)
PRODUCT_DAYS = ("Final Product", "Post-Thaw", "Post-Release")
PRODUCT_SOURCES = ("Outcome",)


def _patient_mask(ctx: C.Ctx) -> pd.Series:
    kind, source, day = (ctx.meta(c).reindex(ctx.params["name"]) for c in
                         (ctx.s.functional_type, ctx.s.variation_source, ctx.s.process_day))
    return (kind.isin(PATIENT_TYPES) | source.isin(PATIENT_SOURCES) | day.isin(PATIENT_DAYS)).reset_index(drop=True)


def _product_mask(ctx: C.Ctx) -> pd.Series:
    source, day = (ctx.meta(c).reindex(ctx.params["name"]) for c in (ctx.s.variation_source, ctx.s.process_day))
    return (day.isin(PRODUCT_DAYS) | source.isin(PRODUCT_SOURCES)).reset_index(drop=True)


def _needs_catalogue(ctx: C.Ctx) -> bool:
    if ctx.s.process_day or ctx.s.functional_type:
        return False
    st.info("The parameter metadata has no Functional Type or Process Day column, so the parameters cannot be grouped. "
            "Add the catalogue under `parameter_metadata.catalog` in the config.")
    return True


def _section(ctx: C.Ctx, names: list[str], key: str) -> None:
    """Scorecard, the picked parameter's trend, and the categorical parameters."""
    name = C.scorecard(ctx, names, key)
    if name is not None:
        C.parameter_detail(ctx, name, key)
    C.categorical_section(ctx, names, key)


def patient() -> None:
    ctx = C.context("Patient and starting material", "What comes in: the patient, the apheresis and the thawed material.")
    if _needs_catalogue(ctx):
        return
    _section(ctx, ctx.names(_patient_mask(ctx)), "patient")


def process() -> None:
    ctx = C.context("Process", "The manufacturing steps, day by day.")
    if _needs_catalogue(ctx):
        return
    s = ctx.s
    inside = ~(_patient_mask(ctx) | _product_mask(ctx))
    day = ctx.meta(s.process_day).reindex(ctx.params["name"]).reset_index(drop=True)
    status = ctx.score.set_index("parameter")["status"]
    days = M.day_order(day[inside & (day != "")])
    if not days:
        st.info("No process parameters found.")
        return

    def label(d: str) -> str:
        names = ctx.params.loc[(inside & (day == d)).to_numpy(), "name"]
        shifted = int((status.reindex(names) == M.STATUS_SHIFTED).sum())
        return f"{d} · {shifted} shifted" if shifted else d

    st.session_state.setdefault("mon_day", "D0" if "D0" in days else days[0])
    if st.session_state["mon_day"] not in days:
        st.session_state["mon_day"] = days[0]
    picked = st.segmented_control("Process day", days, format_func=label, key="mon_day", label_visibility="collapsed") or days[0]
    mask = inside & (day == picked)

    filters = st.columns(2)
    for column, title, slot in ((s.functional_type, "Functional type", filters[0]), (s.variation_source, "Variation source", filters[1])):
        if column:
            meta = ctx.meta(column).reindex(ctx.params["name"]).reset_index(drop=True)
            options = sorted(set(meta[mask]) - {""})
            key = f"mon_process_{title}"
            st.session_state[key] = [x for x in st.session_state.get(key, []) if x in options]
            chosen = slot.multiselect(title, options, placeholder=f"All ({len(options)})", key=key)
            if chosen:
                mask &= meta.isin(chosen)
    names = ctx.names(mask)
    _section(ctx, names, "process")
    _families(ctx, ctx.names(inside))


def _families(ctx: C.Ctx, names: list[str]) -> None:
    families = M.day_families([n for n in names if n in ctx.values])
    if not families:
        return
    with st.expander(f"Across process days ({len(families)} parameters measured on three or more days)"):
        stem = st.selectbox("Parameter", list(families), key="mon_family")
        profile = M.family_profile(ctx.values, families[stem], ctx.recent, ctx.baseline)
        st.plotly_chart(family_figure(profile, stem), width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
        st.caption("Each day is its own measurement of the same quantity; the lines join the medians.")


def product() -> None:
    ctx = C.context("Final product", "Quality attributes, OOS and release.")
    if _needs_catalogue(ctx):
        return
    s, df = ctx.s, ctx.df
    names = ctx.names(_product_mask(ctx))

    if s.oos_flag:
        oos = M.flag(df[s.oos_flag], s.truthy)
        left, right = st.columns(2, gap="medium")
        with left:
            options = [s.oos_flag] + s.oos_types
            column = st.selectbox("OOS over time", options, format_func=M.oos_label, key="mon_oos_type", label_visibility="collapsed")
            f = M.flag(df[column], s.truthy)
            known = ctx.period & f.notna()
            st.plotly_chart(p_chart_figure(S.monthly_rate(ctx.dates[known], f[known].astype(bool)), f"{M.oos_label(column)} rate"),
                            width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
        with right:
            types = M.oos_by_type(df, s, ctx.recent, ctx.baseline)
            if len(types):
                st.plotly_chart(oos_type_figure(types, [M.oos_label(t) for t in types["type"]], "recent", "baseline"),
                                width="stretch", theme="streamlit", config=C.PLOT_CONFIG)
        waiting = int((ctx.recent & oos.isna()).sum())
        if waiting:
            st.caption(f"{waiting} recent batches have no OOS result yet and are left out of the rates.")

    key_cqas = [c for c in s.key_cqas if c in ctx.values]
    if key_cqas:
        C.heading("Key quality attributes", "Grey band: the baseline's middle half. Orange: monthly median. Blue shade: the recent window.")
        status = ctx.score.set_index("parameter")
        for start in range(0, len(key_cqas), 4):
            for slot, name in zip(st.columns(4), key_cqas[start:start + 4]):
                row = status.loc[name] if name in status.index else None
                mark = f" · {C.status_text(row['status'], row['shift'])}" if row is not None and row["status"] != M.STATUS_STABLE else ""
                short = name if len(name) <= 34 else name[:33] + "…"
                slot.plotly_chart(
                    mini_trend_figure(ctx.dates[ctx.period], ctx.values.loc[ctx.period, name], ctx.recent_start,
                                      ctx.baseline[ctx.period], short + mark),
                    width="stretch", theme="streamlit", config=C.PLOT_CONFIG, key=f"mini_{name}",
                )

    C.heading("All final product parameters", "Click a row for its trend.")
    _section(ctx, names, "product")
