package com.vppoc.widget;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.SystemClock;
import android.widget.RemoteViews;

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
        if (ACT.equals(a) || AppWidgetManager.ACTION_APPWIDGET_UPDATE.equals(a)) {
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
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget);
        try {
            JSONObject j = new JSONObject(body == null ? "{}" : body);
            v.setTextViewText(R.id.bal, j.optString("bal_s", "—"));
            String prof = j.optString("profit_s", "—"), mult = j.optString("mult_s", "");
            v.setTextViewText(R.id.year, "Через год: " + j.optString("year_s", "—")
                    + ("—".equals(prof) ? "" : "  (+" + prof + ", " + mult + ")"));
            v.setTextViewText(R.id.line, j.optString("line", ""));
            String w = j.optString("warn", "");
            if (!j.optBoolean("ok", true) && !j.optString("err", "").equals("")) w = j.optString("err", "");
            v.setTextViewText(R.id.warn, err != null ? err : w);
            v.setTextViewText(R.id.upd, err != null ? "было " + prefs(c).getString("last_t", "—") : now);
        } catch (Exception e) {
            v.setTextViewText(R.id.warn, err != null ? err : "ответ бота не читается");
            v.setTextViewText(R.id.upd, now);
        }
        v.setOnClickPendingIntent(R.id.root, refreshIntent(c));
        AppWidgetManager.getInstance(c).updateAppWidget(new ComponentName(c, Widget.class), v);
    }
}
