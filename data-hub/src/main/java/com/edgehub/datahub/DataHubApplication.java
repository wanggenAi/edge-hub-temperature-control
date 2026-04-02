package com.edgehub.datahub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DataHubApplication {

  public static void main(String[] args) {
    SpringApplication.run(DataHubApplication.class, args);
  }
}
