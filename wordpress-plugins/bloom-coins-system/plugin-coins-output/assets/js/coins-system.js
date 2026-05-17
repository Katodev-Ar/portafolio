/**
 * JavaScript del Sistema de Monedas
 * Manga Scan Groups - Coins System
 */

(function($) {
    'use strict';
    
    // Variables globales
    window.msgCoinsSystem = {
        userBalance: msgCoins.user_balance || 0,
        ajaxUrl: msgCoins.ajax_url,
        
        /**
         * Inicializar el sistema
         */
        init: function() {
            this.bindEvents();
            this.updateBalanceDisplay();
        },
        
        /**
         * Vincular eventos
         */
        bindEvents: function() {
            // Event listeners ya están en los botones inline
            console.log('[MSG Coins] Sistema de monedas inicializado');
        },
        
        /**
         * Actualizar display de saldo en toda la página
         */
        updateBalanceDisplay: function() {
            const balanceElements = document.querySelectorAll('.msg-user-balance, .msg-wallet-balance, .msg-balance-value');
            balanceElements.forEach(el => {
                el.textContent = this.formatNumber(this.userBalance);
            });
        },
        
        /**
         * Formatear número con separadores de miles
         */
        formatNumber: function(num) {
            return parseInt(num).toLocaleString();
        },
        
        /**
         * Mostrar notificación toast
         */
        showToast: function(message, type = 'success') {
            const toast = document.createElement('div');
            toast.className = 'msg-toast' + (type === 'error' ? ' msg-error' : '');
            toast.textContent = message;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.style.animation = 'msgSlideOut 0.3s ease-out';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        },
        
        /**
         * Desbloquear capítulo
         */
        unlockChapter: function(chapterId, coinPrice, nonce) {
            return fetch(this.ajaxUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    action: 'unlock_chapter',
                    chapter_id: chapterId,
                    nonce: nonce
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.userBalance -= coinPrice;
                    this.updateBalanceDisplay();
                    this.showToast(data.data.message, 'success');
                    
                    // Recargar después de 1 segundo
                    setTimeout(() => location.reload(), 1000);
                } else {
                    this.showToast(data.data.message, 'error');
                }
                
                return data;
            })
            .catch(error => {
                this.showToast('Error de conexión', 'error');
                throw error;
            });
        },
        
        /**
         * Comprar monedas (simulación)
         */
        buyCoins: function(coins, price, nonce) {
            return fetch(this.ajaxUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    action: 'simulate_coin_purchase',
                    coins: coins,
                    price: price,
                    nonce: nonce
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.userBalance = parseInt(this.userBalance) + parseInt(coins);
                    this.updateBalanceDisplay();
                    this.showToast('✅ Compra exitosa! +' + coins + ' monedas', 'success');
                } else {
                    this.showToast(data.data.message, 'error');
                }
                
                return data;
            })
            .catch(error => {
                this.showToast('Error de conexión', 'error');
                throw error;
            });
        }
    };
    
    // Inicializar cuando el DOM esté listo
    $(document).ready(function() {
        window.msgCoinsSystem.init();
    });
    
    // Agregar animación de slideOut
    const style = document.createElement('style');
    style.textContent = `
        @keyframes msgSlideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(400px);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
    
})(jQuery);
