from django.db.models import Transform, DateTimeField, IntegerField


class DateTimeLocal(Transform):
    lookup_name = 'local'

    def as_sql(self, compiler, connection):
        lhs, params = compiler.compile(self.lhs)
        dt = lhs  # has quotes like "table_name"."date_time"
        tz = lhs[:-1] + "_tz" + lhs[-1]  # Add _tz to field name
        return f"{dt} AT TIME ZONE {tz}", params


DateTimeField.register_lookup(DateTimeLocal)


class MonthWeek(Transform):
    lookup_name = 'month_week'

    @property
    def output_field(self):
        return IntegerField()

    def as_sql(self, compiler, connection):
        lhs, params = compiler.compile(self.lhs)
        return f"TO_CHAR( {lhs}, 'W' )::integer", params


DateTimeField.register_lookup(MonthWeek)

