export function dataSourceType(value: string) {
  return (
    (
      { postgres: 'PostgreSQL', mysql: 'MySQL', mssql: 'SQL Server', excel: 'Excel', powerbi: 'Power BI' } as Record<
        string,
        string
      >
    )[value] ?? value
  );
}
