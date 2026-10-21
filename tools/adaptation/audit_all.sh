cd /tmp/claude-0/-home-user-vp-poc-screener/591d3753-67a7-5ebe-97a8-1553972a4a6c/scratchpad/zr
for t in t_emx_deep t_emx_lv t_rbx_lim t_prx_lim t_cas_settle t_nx_lim t_zm_far t_bn_trigger t_universe t_rbx_coins t_ls_d24 t_gatefill_ui; do
  echo "### $t"; timeout 2400 python3 $t.py 2>&1 | grep -vi "warn\|GET /\|POST /\|Running on\|Press CTRL\|development server\|Serving Flask" | tail -3
done
echo AUDIT-DONE
