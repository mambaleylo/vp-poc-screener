package com.vppoc.widget;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.SystemClock;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.DashPathEffect;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Shader;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** The home-screen widget: the bot's /api/widget (the balance and the year if it goes like the last n days of real ⚡ trades),
 *  refreshed every 15 min (an inexact alarm), on a tap and by the system's own 30-min update. The last good answer is kept
 *  and shown with "нет связи" when the bot cannot be reached. */
public class Widget extends AppWidgetProvider {
    static final String ACT = "com.vppoc.widget.REFRESH";
    static final String DEF_ADDR = "192.168.100.66:8070";
    static final long EVERY = 15 * 60 * 1000L;

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("vp", Context.MODE_PRIVATE); }
    static String addr(Context c) { return prefs(c).getString("addr", DEF_ADDR); }

    static PendingIntent refreshIntent(Context c) {
        Intent i = new Intent(c, Widget.class).setAction(ACT);
        return PendingIntent.getBroadcast(c, 0, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void schedule(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        am.setInexactRepeating(AlarmManager.ELAPSED_REALTIME, SystemClock.elapsedRealtime() + EVERY, EVERY, refreshIntent(c));
    }

    @Override
    public void onReceive(Context c, Intent i) {
        String a = i.getAction();
        if (ACT.equals(a) || AppWidgetManager.ACTION_APPWIDGET_UPDATE.equals(a) || AppWidgetManager.ACTION_APPWIDGET_OPTIONS_CHANGED.equals(a)) {
            if (!ids(c).equals("")) schedule(c);
            final PendingResult pr = goAsync();
            final Context app = c.getApplicationContext();
            new Thread(new Runnable() {
                public void run() {
                    try { update(app); } finally { pr.finish(); }
                }
            }).start();
        } else if (AppWidgetManager.ACTION_APPWIDGET_DISABLED.equals(a)) {
            ((AlarmManager) c.getSystemService(Context.ALARM_SERVICE)).cancel(refreshIntent(c));
        } else {
            super.onReceive(c, i);
        }
    }

    static String ids(Context c) {
        int[] x = AppWidgetManager.getInstance(c).getAppWidgetIds(new ComponentName(c, Widget.class));
        return x.length == 0 ? "" : String.valueOf(x.length);
    }

    static String fetch(String addr) throws Exception {
        HttpURLConnection h = (HttpURLConnection) new URL("http://" + addr + "/api/widget").openConnection();
        h.setConnectTimeout(8000); h.setReadTimeout(15000);
        try {
            InputStream in = h.getInputStream();
            ByteArrayOutputStream b = new ByteArrayOutputStream(); byte[] buf = new byte[4096]; int n;
            while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
            return b.toString("UTF-8");
        } finally { h.disconnect(); }
    }

    static int dp(Context c, float v) { return Math.round(v * c.getResources().getDisplayMetrics().density); }

    /** the balance curve along the trades (the bot's "curve": [days, $]) as a bitmap of the chart's size */
    static Bitmap chart(Context c, JSONArray pts, int w, int h) {
        Bitmap b = Bitmap.createBitmap(Math.max(w, 10), Math.max(h, 10), Bitmap.Config.ARGB_8888);
        Canvas cv = new Canvas(b);
        Paint tx = new Paint(Paint.ANTI_ALIAS_FLAG); tx.setColor(0xFF6B7684); tx.setTextSize(dp(c, 10));
        if (pts == null || pts.length() < 2) {
            cv.drawText("график появится после первых сделок", 0, h / 2f, tx);
            return b;
        }
        int n = pts.length(); float[] xs = new float[n], ys = new float[n];
        float x0 = 0, x1 = 0, lo = Float.MAX_VALUE, hi = -Float.MAX_VALUE;
        for (int i = 0; i < n; i++) {
            JSONArray p = pts.optJSONArray(i);
            xs[i] = (float) p.optDouble(0); ys[i] = (float) p.optDouble(1);
            lo = Math.min(lo, ys[i]); hi = Math.max(hi, ys[i]);
        }
        x0 = xs[0]; x1 = Math.max(xs[n - 1], x0 + 1e-3f);
        if (hi - lo < 1e-6f) { hi += 1; lo -= 1; }
        float pad = dp(c, 4), lab = dp(c, 13), top = pad, bot = h - lab, left = 0, right = w - dp(c, 6);
        Path line = new Path(), fill = new Path();
        for (int i = 0; i < n; i++) {
            float X = left + (xs[i] - x0) / (x1 - x0) * (right - left), Y = bot - (ys[i] - lo) / (hi - lo) * (bot - top);
            if (i == 0) { line.moveTo(X, Y); fill.moveTo(X, bot); }
            line.lineTo(X, Y); fill.lineTo(X, Y);
            xs[i] = X; ys[i] = Y;
        }
        fill.lineTo(xs[n - 1], bot); fill.close();
        boolean up = ys[n - 1] <= ys[0];
        int col = up ? 0xFF4ADE80 : 0xFFF87171;
        Paint f = new Paint(Paint.ANTI_ALIAS_FLAG);
        f.setShader(new LinearGradient(0, top, 0, bot, (col & 0x00FFFFFF) | 0x55000000, col & 0x00FFFFFF, Shader.TileMode.CLAMP));
        cv.drawPath(fill, f);
        Paint base = new Paint(Paint.ANTI_ALIAS_FLAG); base.setColor(0x33FFFFFF); base.setStrokeWidth(dp(c, 1));
        base.setPathEffect(new DashPathEffect(new float[]{dp(c, 4), dp(c, 4)}, 0));
        cv.drawLine(left, ys[0], right, ys[0], base);
        Paint ln = new Paint(Paint.ANTI_ALIAS_FLAG); ln.setColor(col); ln.setStyle(Paint.Style.STROKE);
        ln.setStrokeWidth(dp(c, 2.2f)); ln.setStrokeJoin(Paint.Join.ROUND); ln.setStrokeCap(Paint.Cap.ROUND);
        cv.drawPath(line, ln);
        Paint dot = new Paint(Paint.ANTI_ALIAS_FLAG); dot.setColor(col);
        cv.drawCircle(xs[n - 1], ys[n - 1], dp(c, 3.5f), dot);
        float days = x1 - x0;
        cv.drawText(days >= 1 ? Math.round(days) + " дн назад" : "сегодня", left, h - dp(c, 2), tx);
        tx.setTextAlign(Paint.Align.RIGHT);
        cv.drawText("сейчас", right, h - dp(c, 2), tx);
        return b;
    }

    static void update(Context c) {
        String now = new SimpleDateFormat("HH:mm", Locale.getDefault()).format(new Date());
        String body = null, err = null;
        try {
            body = fetch(addr(c));
            new JSONObject(body);
            prefs(c).edit().putString("last", body).putString("last_t", now).apply();
        } catch (Exception e) {
            err = "нет связи с ботом " + addr(c);
            body = prefs(c).getString("last", null);
        }
        AppWidgetManager mgr = AppWidgetManager.getInstance(c);
        for (int id : mgr.getAppWidgetIds(new ComponentName(c, Widget.class))) {
            RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget);
            try {
                JSONObject j = new JSONObject(body == null ? "{}" : body);
                v.setTextViewText(R.id.bal, j.optString("bal_s", "—"));
                v.setTextViewText(R.id.year, j.optString("year_k", j.optString("year_s", "—")));
                String prof = j.optString("profit_k", "—"), mult = j.optString("mult_s", "");
                v.setTextViewText(R.id.mult, "—".equals(prof) ? "" : "+" + prof + " · " + mult);
                v.setTextViewText(R.id.mods, j.optString("mods_s", ""));
                String line = j.optString("line", "");
                if (!j.optBoolean("ok", true) && !j.optString("err", "").equals("")) line = j.optString("err", "");
                v.setTextViewText(R.id.line, err != null ? err : line);
                v.setTextViewText(R.id.warn, j.optString("warn", "").equals("") ? "" : "⚠ мало сделок");
                v.setTextViewText(R.id.upd, err != null ? "было " + prefs(c).getString("last_t", "—") : now);
                Bundle o = mgr.getAppWidgetOptions(id);
                int wdp = o.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 300), hdp = o.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 180);
                if (wdp <= 0) wdp = 300;
                if (hdp <= 0) hdp = 180;
                int cw = dp(c, wdp - 32), ch = Math.max(dp(c, 36), dp(c, hdp - 150));
                v.setImageViewBitmap(R.id.chart, chart(c, j.optJSONArray("curve"), cw, ch));
            } catch (Exception e) {
                v.setTextViewText(R.id.line, err != null ? err : "ответ бота не читается");
                v.setTextViewText(R.id.upd, now);
            }
            v.setOnClickPendingIntent(R.id.root, refreshIntent(c));
            mgr.updateAppWidget(id, v);
        }
    }
}
