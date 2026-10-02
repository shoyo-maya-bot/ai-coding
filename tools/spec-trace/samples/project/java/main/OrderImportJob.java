package com.example.batch.order;

public class OrderImportJob {
    private final OrderRepository repository;

    public OrderImportJob(OrderRepository repository) {
        this.repository = repository;
    }

    public int importOrders(java.util.List<Order> orders) {
        int added = 0;
        for (Order o : orders) {
            if (repository.exists(o.orderNo())) {
                continue; // 冪等
            }
            repository.insert(o);
            added++;
        }
        return added;
    }
}
