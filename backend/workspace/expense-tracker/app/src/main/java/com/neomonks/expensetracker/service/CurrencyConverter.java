
```java
package com.neomonks.expensetracker.service;

import java.util.HashMap;
import java.util.Map;

public class CurrencyConverter {

    private Map<String, Double> exchangeRates;

    public CurrencyConverter() {
        this.exchangeRates = new HashMap<>();
        // Initialize with some currency rates
        exchangeRates.put("USD", 1.0);
        exchangeRates.put("EUR", 0.85);
        exchangeRates.put("GBP", 0.75);
        exchangeRates.put("JPY", 110.0);
    }

    public double convert(double amount, String fromCurrency, String toCurrency) {
        if (!exchangeRates.containsKey(fromCurrency) || !exchangeRates.containsKey(toCurrency)) {
            throw new IllegalArgumentException("Invalid currency code");
        }
        return amount * (exchangeRates.get(toCurrency) / exchangeRates.get(fromCurrency));
    }

    public void updateExchangeRate(String currencyCode, double rate) {
        exchangeRates.put(currencyCode, rate);
    }

}