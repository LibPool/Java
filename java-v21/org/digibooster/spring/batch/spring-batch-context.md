# spring-batch-context

> 标签: github, Java 8+

## 简介

The aim of this library is to allow developers who use spring-batch to propagate information from the main thread that runs the batch to the executions context of the batch items : ItemReader, ItemProcessor and ItemWriter. For example we some times need to extract the current user from Security Context, so instead of writing the code that passes the current user information as a job parameter we let this library to handle it. This library can be extended to support any information developer want to add.

最低 Java 版本：Java 8；已收录于 java-v8, java-v11, java-v17, java-v21, java-v25, java-v26。

## 官网

- https://github.com/zahidMed/spring-batch-context

## 历史版本号

- 1.0.0
- 1.1.0-RELEASE

## 获取地址

- Maven 仓库地址：https://repo.maven.apache.org/maven2/org/digibooster/spring/batch/spring-batch-context/
- Maven 坐标：`org.digibooster.spring.batch:spring-batch-context`
- pom.xml 引用：`<dependency><groupId>org.digibooster.spring.batch</groupId><artifactId>spring-batch-context</artifactId><version>1.1.0-RELEASE</version></dependency>`
