from django.db.models import Transform, DateTimeField, IntegerField


class MonthWeek(Transform):
    lookup_name = 'month_week'

    @property
    def output_field(self):
        return IntegerField()

    def as_sql(self, compiler, connection):
        lhs, params = compiler.compile(self.lhs)
        return f"TO_CHAR( {lhs}, 'W' )::integer", params


DateTimeField.register_lookup(MonthWeek)

