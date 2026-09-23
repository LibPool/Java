# spring-jdbc-oracle-parent

> 标签: github, Java 8+

## 简介

A variant of Spring's JdbcTemplate that uses Oracle Update Batching. If Spring's classic JdbcTemplate is used in combination with an Oracle DB, the `batchUpdate()` methods won't return the number of affected rows. Instead, these methods do always return an array containing -2 (`Statement#SUCCESS_NO_INFO`) in each element. In order to get the number of affected rows during a batch INSERT/UPDATE/DELETE, it is required to use [Oracle Update Batching](http://docs.oracle.com/cd/B28359_01/java.111/b31224/oraperf.htm#autoId2).

最低 Java 版本：Java 8；已收录于 java-v8, java-v11, java-v17, java-v21, java-v25, java-v26。

## 官网

- https://github.com/ferstl/spring-jdbc-oracle

## 历史版本号

- 0.9.0
- 1.0.0
- 2.0.0

## 获取地址

- Maven 仓库地址：https://repo.maven.apache.org/maven2/com/github/ferstl/spring-jdbc-oracle-parent/
- Maven 坐标：`com.github.ferstl:spring-jdbc-oracle-parent`
- pom.xml 引用：`<dependency><groupId>com.github.ferstl</groupId><artifactId>spring-jdbc-oracle-parent</artifactId><version>2.0.0</version></dependency>`
