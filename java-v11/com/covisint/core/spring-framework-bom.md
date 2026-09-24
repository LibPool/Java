# spring-framework-bom

> 标签: Java, Java 8+

## 简介

<![CDATA[ This bill of materials (BOM) POM covers all the Spring artifacts related to a particular version. By importing this BOM, you fix the version of all of Spring-related artifacts to the versions associated with a particular release. This prevents the overriding of Spring transitive dependencies which in turn could cause version conflicts between libraries. To use this BOM, add the following in your POM: <dependencyManagement> <dependencies> <dependency> <groupId>com.covisint.core</groupId> <artifactId>springframework-bom</artifactId> <version>4.0.2.RELEASE</version> <type>pom</type> <scope>import</scope> </dependency> </dependencies> </dependencyManagement> And then declare your dependency on the Spring artifacts *without* a version. ]]>

最低 Java 版本：Java 8；已收录于 java-v8, java-v11, java-v17, java-v21, java-v25, java-v26。

## 官网

- http://covisint.com

## 历史版本号

- 4.0.2.RELEASE

## 获取地址

- Maven 仓库地址：https://repo.maven.apache.org/maven2/com/covisint/core/spring-framework-bom/
- Maven 坐标：`com.covisint.core:spring-framework-bom`
- pom.xml 引用：`<dependency><groupId>com.covisint.core</groupId><artifactId>spring-framework-bom</artifactId><version>4.0.2.RELEASE</version></dependency>`
- 源码仓库：http://github.com/Covisint
