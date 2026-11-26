// The words of the Vitals page's "Worth checking" list (#75), in English, Ukrainian and Spanish.
// Neutral by rule: a lasting change from your own usual is worth a look, never an alarm, and an
// empty list never claims all is fine. A plural key has _one/_few/_many/_other forms,
// picked with Intl.PluralRules, falling back to the bare key's _other.

export const SUSTAINED_LANGS = ["en", "uk", "es"];
const LOCALES = { en: "en-GB", uk: "uk-UA", es: "es-ES" };

const EN = {
  "title": "Worth checking",
  "note": "Changes that lasted: days in a row outside your own usual range, or heart rate well above your resting level while you were still. Not a diagnosis — a cold, short sleep, alcohol, travel, heat or hard training can all do this.",
  "empty": "In these days nothing stayed outside your usual range of resting heart rate or HRV for {days} in a row. This only covers what the watch recorded.",
  "not_enough": "Not checked: there are fewer than {min} days of values in the {days} days before, so there is no usual range to compare with yet.",
  "metric.resting_hr": "Resting heart rate",
  "metric.hrv": "HRV",
  "metric.heart_rate": "Heart rate while still",
  "unit.resting_hr": "bpm",
  "unit.hrv": "ms",
  "unit.heart_rate": "bpm",
  "and": " and ",
  "period": "{first} – {last}",
  "days_one": "{n} day",
  "days_other": "{n} days",
  "up": "{metric}: {delta} {unit} above your usual {usual} {unit} on average, {days} in a row",
  "down": "{metric}: {delta} {unit} below your usual {usual} {unit} on average, {days} in a row",
  "together_one": "Both on {n} day",
  "together_other": "Both on {n} of the same days",
  "minutes": "{date}, {from}–{to} · {n} min",
  "minutes.line": "On average {mean} bpm, {delta} above your usual resting {usual} bpm, with no steps recorded",
  "context.workout": "Workout on {day}",
  "context.workout_detail": "Workout on {day}: {type}, {minutes} min",
  "context.beta_blocker": "{name}: a beta blocker, which lowers heart rate and can hide a rise",
  "area": "worth checking",
  "footnote": "How this is found: your usual range is the median and spread of the {baseline} days before; {days} in a row beyond it count (resting heart rate up by at least {rhr} bpm, HRV down by at least {hrv} ms). Heart rate counts when it is {above} bpm above your resting median for {minutes}+ minutes with no steps and no workout (Apple Health only). These thresholds are initial defaults, to be reviewed. {limits}",
  "limits": "No ECG: wrist sensors only. Days and minutes when the watch was off are gaps, not normal days.",
};

const UK = {
  "title": "Варто переглянути",
  "note": "Зміни, що тривали: кілька днів поспіль поза вашим власним звичним діапазоном, або пульс значно вищий за ваш пульс спокою, коли ви не рухалися. Це не діагноз — так буває через застуду, короткий сон, алкоголь, подорож, спеку чи важке тренування.",
  "empty": "За ці дні пульс спокою та HRV не виходили за ваш звичний діапазон {days} поспіль. Це стосується лише того, що записав годинник.",
  "not_enough": "Не перевірено: за попередні {days} днів є менше ніж {min} днів зі значеннями, тож звичного діапазону для порівняння ще немає.",
  "metric.resting_hr": "Пульс спокою",
  "metric.hrv": "HRV",
  "metric.heart_rate": "Пульс у спокої",
  "unit.resting_hr": "уд/хв",
  "unit.hrv": "мс",
  "unit.heart_rate": "уд/хв",
  "and": " і ",
  "period": "{first} – {last}",
  "days_one": "{n} день",
  "days_few": "{n} дні",
  "days_many": "{n} днів",
  "days_other": "{n} дня",
  "up": "{metric}: у середньому на {delta} {unit} вище за ваш звичний {usual} {unit}, {days} поспіль",
  "down": "{metric}: у середньому на {delta} {unit} нижче за ваш звичний {usual} {unit}, {days} поспіль",
  "together_one": "Обидва — {n} день",
  "together_few": "Обидва — у ті самі {n} дні",
  "together_many": "Обидва — у ті самі {n} днів",
  "together_other": "Обидва — у ті самі {n} дня",
  "minutes": "{date}, {from}–{to} · {n} хв",
  "minutes.line": "У середньому {mean} уд/хв, на {delta} вище за ваш звичний пульс спокою {usual} уд/хв, кроків не записано",
  "context.workout": "Тренування {day}",
  "context.workout_detail": "Тренування {day}: {type}, {minutes} хв",
  "context.beta_blocker": "{name}: бета-блокатор, він знижує пульс і може приховати підвищення",
  "area": "варто переглянути",
  "footnote": "Як це визначено: ваш звичний діапазон — медіана й розкид за {baseline} попередніх днів; рахуються {days} поспіль поза ним (пульс спокою вищий щонайменше на {rhr} уд/хв, HRV нижча щонайменше на {hrv} мс). Пульс рахується, коли він на {above} уд/хв вищий за медіану пульсу спокою {minutes}+ хвилин без кроків і без тренування (лише Apple Health). Ці пороги — початкові, їх ще треба переглянути. {limits}",
  "limits": "Без ЕКГ: лише датчики на зап'ясті. Дні й хвилини, коли годинник був знятий, — це прогалини, а не звичайні дні.",
};

const ES = {
  "title": "Para revisar",
  "note": "Cambios que se mantuvieron: varios días seguidos fuera de su propio rango habitual, o un pulso bastante por encima de su pulso en reposo estando quieto. No es un diagnóstico: un resfriado, dormir poco, el alcohol, un viaje, el calor o un entrenamiento duro pueden causarlo.",
  "empty": "En estos días ni el pulso en reposo ni la VFC salieron de su rango habitual {days} seguidos. Esto solo abarca lo que registró el reloj.",
  "not_enough": "Sin comprobar: hay menos de {min} días con valores en los {days} días anteriores, así que aún no hay un rango habitual con el que comparar.",
  "metric.resting_hr": "Pulso en reposo",
  "metric.hrv": "VFC",
  "metric.heart_rate": "Pulso estando quieto",
  "unit.resting_hr": "lpm",
  "unit.hrv": "ms",
  "unit.heart_rate": "lpm",
  "and": " y ",
  "period": "{first} – {last}",
  "days_one": "{n} día",
  "days_other": "{n} días",
  "up": "{metric}: de media {delta} {unit} por encima de su valor habitual de {usual} {unit}, {days} seguidos",
  "down": "{metric}: de media {delta} {unit} por debajo de su valor habitual de {usual} {unit}, {days} seguidos",
  "together_one": "Ambos durante {n} día",
  "together_other": "Ambos durante {n} de los mismos días",
  "minutes": "{date}, {from}–{to} · {n} min",
  "minutes.line": "De media {mean} lpm, {delta} por encima de su pulso en reposo habitual de {usual} lpm, sin pasos registrados",
  "context.workout": "Entrenamiento el {day}",
  "context.workout_detail": "Entrenamiento el {day}: {type}, {minutes} min",
  "context.beta_blocker": "{name}: un betabloqueante, que baja el pulso y puede ocultar una subida",
  "area": "para revisar",
  "footnote": "Cómo se detecta: su rango habitual es la mediana y la dispersión de los {baseline} días anteriores; cuentan {days} seguidos fuera de él (pulso en reposo al menos {rhr} lpm más alto, VFC al menos {hrv} ms más baja). El pulso cuenta cuando está {above} lpm por encima de su mediana en reposo durante {minutes}+ minutos sin pasos ni entrenamiento (solo Apple Health). Estos umbrales son valores iniciales, pendientes de revisión. {limits}",
  "limits": "Sin ECG: solo sensores de muñeca. Los días y minutos sin el reloj son huecos, no días normales.",
};

export const SUSTAINED_DICTIONARIES = { en: EN, uk: UK, es: ES };

/** { t, tn } for one language; a missing key falls back to English, an unknown language is English. */
export function sustainedTranslator(lang) {
  const code = SUSTAINED_LANGS.includes(lang) ? lang : "en";
  const dict = SUSTAINED_DICTIONARIES[code];
  const plural = new Intl.PluralRules(LOCALES[code]);
  const fill = (text, vars) => text.replace(/\{(\w+)\}/g, (whole, name) => vars[name] ?? whole);
  const t = (key, vars = {}) => fill(dict[key] ?? EN[key] ?? key, vars);
  const tn = (key, vars) => {
    const text = dict[`${key}_${plural.select(vars.n)}`] ?? dict[`${key}_other`]
      ?? EN[`${key}_${new Intl.PluralRules("en").select(vars.n)}`] ?? key;
    return fill(text, vars);
  };
  return { lang: code, t, tn };
}
