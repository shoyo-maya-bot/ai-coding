package com.example.batch.order;

import static org.assertj.core.api.Assertions.assertThat;

class OrderImportJobTest {
    @Test
    void importOrders_skipsExisting() {
        var repo = new InMemoryOrderRepository();
        var job = new OrderImportJob(repo);
        assertThat(job.importOrders(List.of(new Order("A1", 1)))).isEqualTo(1);
        assertThat(job.importOrders(List.of(new Order("A1", 1)))).isEqualTo(0);
    }
}
