package com.edgehub.datahub.config;

import java.time.Duration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
@ConditionalOnProperty(prefix = "datahub.redis", name = "enabled", havingValue = "true")
public class RedisConfig {

  @Bean
  public LettuceConnectionFactory redisConnectionFactory(HubProperties properties) {
    HubProperties.Redis redis = properties.getRedis();
    RedisStandaloneConfiguration standalone = new RedisStandaloneConfiguration(redis.getHost(), redis.getPort());
    standalone.setDatabase(redis.getDatabase());
    if (redis.getPassword() != null && !redis.getPassword().isBlank()) {
      standalone.setPassword(RedisPassword.of(redis.getPassword()));
    }

    LettuceClientConfiguration clientConfig =
        LettuceClientConfiguration.builder()
            .commandTimeout(Duration.ofMillis(Math.max(1000L, redis.getConnectTimeoutMs())))
            .shutdownTimeout(Duration.ofSeconds(1))
            .build();
    return new LettuceConnectionFactory(standalone, clientConfig);
  }

  @Bean
  public StringRedisTemplate stringRedisTemplate(LettuceConnectionFactory redisConnectionFactory) {
    return new StringRedisTemplate(redisConnectionFactory);
  }
}
