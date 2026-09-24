# infinispan-spring5-parent

> 标签: Java, Java 8+

## 简介

The Infinispan Spring Integration project provides Spring integration for Infinispan, a high performance distributed cache. Its primary features are * An implementation of org.springframework.cache.CacheManager, Spring's central caching abstraction, backed by Infinispan's EmbeddedCacheManager. To be used if your Spring-powered application and Infinispan are colocated, i.e. running within the same VM. * An implementation of org.springframework.cache.CacheManager backed by Infinispan's RemoteCacheManager. To bes used if your Spring-powered application accesses Infinispan remotely, i.e. over the network. * An implementation of org.springframework.cache.CacheManager backed by a CacheContainer reference. To be used if your Spring- powered application needs access to a CacheContainer defined outside the application (e.g. retrieved from JNDI) * Spring namespace support allowing shortcut definitions for all the components above In addition, Infinispan Spring Integration offers various FactoryBeans for facilitating creation of Infinispan core classes - Cache, CacheManager, ... - within a Spring context.

最低 Java 版本：Java 8；已收录于 java-v8, java-v11, java-v17, java-v21, java-v25, java-v26。

## 官网

- https://central.sonatype.com/artifact/org.infinispan%3Ainfinispan-spring5-parent

## 历史版本号

- 14.0.26.Final
- 14.0.27.Final
- 14.0.28.Final
- 14.0.29.Final
- 14.0.30.Final
- 14.0.31.Final
- 14.0.32.Final
- 14.0.33.Final
- 14.0.34.Final
- 14.0.35.Final
- 共 173 个版本，完整清单见 Maven Central。

## 获取地址

- Maven 仓库地址：https://repo.maven.apache.org/maven2/org/infinispan/infinispan-spring5-parent/
- Maven 坐标：`org.infinispan:infinispan-spring5-parent`
- pom.xml 引用：`<dependency><groupId>org.infinispan</groupId><artifactId>infinispan-spring5-parent</artifactId><version>14.0.35.Final</version></dependency>`
