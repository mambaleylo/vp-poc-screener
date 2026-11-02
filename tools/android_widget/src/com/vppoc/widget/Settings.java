package com.vppoc.widget;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** The app's only screen: the bot's address, a check of its answer, how to add the widget. */
public class Settings extends Activity {
    TextView out;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        int p = (int) (16 * getResources().getDisplayMetrics().density);
        LinearLayout l = new LinearLayout(this); l.setOrientation(LinearLayout.VERTICAL); l.setPadding(p, p, p, p);
        TextView t = new TextView(this); t.setTextSize(16);
        t.setText("Адрес бота (IP:порт). Виджет: долгое нажатие на рабочем столе → Виджеты → «VP-POC баланс». "
                + "Нажатие на виджет обновляет его, сам он обновляется раз в 15 минут.");
        final EditText e = new EditText(this); e.setText(Widget.addr(this)); e.setSingleLine(true);
        Button s = new Button(this); s.setText("Сохранить и проверить");
        out = new TextView(this); out.setTextIsSelectable(true);
        l.addView(t); l.addView(e); l.addView(s); l.addView(out);
        setContentView(l);
        s.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                final String a = e.getText().toString().trim().replaceFirst("^https?://", "").replaceAll("/+$", "");
                Widget.prefs(Settings.this).edit().putString("addr", a).apply();
                out.setText("проверяю http://" + a + "/api/widget …");
                new Thread(new Runnable() {
                    public void run() {
                        String r;
                        try { r = "ответ бота:\n" + Widget.fetch(a); } catch (Exception x) { r = "нет связи: " + x; }
                        final String rr = r;
                        runOnUiThread(new Runnable() { public void run() { out.setText(rr); } });
                    }
                }).start();
                sendBroadcast(new Intent(Settings.this, Widget.class).setAction(Widget.ACT));
            }
        });
    }
}
