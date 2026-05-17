<?php if ( ! defined( 'ABSPATH' ) ) exit;
$pos  = $s['banner_position'];
$lang = $s['admin_lang'] ?? 'es';
$l    = BCM_Settings::lang_strings( $lang );
?>
<!-- Bloom Cookie Manager Banner v1.6.0 -->
<div id="bcm-banner" class="bcm-banner bcm-pos-<?php echo esc_attr( $pos ); ?>"
     role="dialog" aria-modal="true"
     aria-label="<?php echo esc_attr( $l['banner_title'] ); ?>"
     style="
         --bcm-bg:       <?php echo esc_attr( $s['bg_color'] ); ?>;
         --bcm-fg:       <?php echo esc_attr( $s['text_color'] ); ?>;
         --bcm-primary:  <?php echo esc_attr( $s['primary_color'] ); ?>;
         --bcm-accept-bg:<?php echo esc_attr( $s['btn_accept_bg'] ); ?>;
         --bcm-reject-bg:<?php echo esc_attr( $s['btn_reject_bg'] ); ?>;
         --bcm-reject-fg:<?php echo esc_attr( $s['btn_reject_text'] ); ?>;
     ">

    <div class="bcm-banner-inner-wrap">

    <!-- ROW 1: texto + botones -->
    <div class="bcm-row bcm-row-main">
        <div class="bcm-banner-text">
            <strong class="bcm-banner-title"><?php echo esc_html( $s['banner_title'] ); ?></strong>
            <p class="bcm-banner-desc">
                <?php echo esc_html( $s['banner_description'] ); ?>
                <?php if ( ! empty( $s['privacy_policy_url'] ) ) : ?>
                    <a href="<?php echo esc_url( $s['privacy_policy_url'] ); ?>"
                       target="_blank" rel="noopener noreferrer"
                       class="bcm-privacy-link">
                        <?php echo esc_html( $l['privacy_link_text'] ); ?>
                    </a>
                <?php endif; ?>
            </p>
        </div>

        <div class="bcm-banner-actions">
            <?php if ( $s['show_customize_btn'] ) : ?>
            <button id="bcm-btn-customize" class="bcm-btn-customize">
                <?php echo esc_html( $s['customize_btn_text'] ); ?>
            </button>
            <?php endif; ?>
            <?php if ( $s['show_reject_btn'] ) : ?>
            <button id="bcm-btn-reject" class="bcm-btn-reject">
                <?php echo esc_html( $s['reject_btn_text'] ); ?>
            </button>
            <?php endif; ?>
            <button id="bcm-btn-accept" class="bcm-btn-accept">
                <?php echo esc_html( $s['accept_btn_text'] ); ?>
            </button>
        </div>
    </div>

    <!-- ROW 2: T&C checkbox (fila separada, visible y ordenada) -->
    <?php if ( ! empty( $s['show_tos_checkbox'] ) ) : ?>
    <div class="bcm-row bcm-row-tos">
        <label class="bcm-tos-label">
            <input type="checkbox" id="bcm-tos-check" class="bcm-tos-check">
            <span class="bcm-tos-text">
                <?php echo esc_html( $l['tos_label'] ); ?>
                <?php if ( ! empty( $s['tos_url'] ) ) : ?>
                    <a href="<?php echo esc_url( $s['tos_url'] ); ?>"
                       target="_blank" rel="noopener noreferrer"
                       class="bcm-tos-link"><?php echo esc_html( $l['tos_link_text'] ); ?></a>
                <?php else : ?>
                    <span class="bcm-tos-nolink"><?php echo esc_html( $l['tos_link_text'] ); ?></span>
                <?php endif; ?>
                <?php if ( ! empty( $s['privacy_policy_url'] ) ) : ?>
                    <?php echo esc_html( $l['tos_and'] ); ?>
                    <a href="<?php echo esc_url( $s['privacy_policy_url'] ); ?>"
                       target="_blank" rel="noopener noreferrer"
                       class="bcm-tos-link"><?php echo esc_html( $l['privacy_link_text'] ); ?></a>
                <?php endif; ?>
                <span class="bcm-tos-cookie-note">
                    <?php echo esc_html( $lang === 'es'
                        ? '(requerido para aceptar cookies)'
                        : '(required to accept cookies)' ); ?>
                </span>
            </span>
        </label>
        <span id="bcm-tos-error" class="bcm-tos-error" style="display:none;" role="alert">
            ⚠ <?php echo esc_html( $l['tos_error'] ); ?>
        </span>
    </div>
    <?php endif; ?>

    <div class="bcm-powered">Powered by Bloom Cookie Manager</div>

    </div><!-- /.bcm-banner-inner-wrap -->
</div>

<!-- Preferences Panel -->
<div id="bcm-preferences" class="bcm-preferences" style="display:none;"
     role="dialog" aria-modal="true"
     aria-label="<?php echo esc_attr( $l['pref_title'] ); ?>">
    <div class="bcm-pref-overlay"></div>
    <div class="bcm-pref-panel" style="--bcm-primary: <?php echo esc_attr( $s['primary_color'] ); ?>;">
        <div class="bcm-pref-header">
            <h2><?php echo esc_html( $l['pref_title'] ); ?></h2>
            <button class="bcm-pref-close" aria-label="<?php echo esc_attr( $lang === 'en' ? 'Close' : 'Cerrar' ); ?>">✕</button>
        </div>
        <div class="bcm-pref-body">
            <p><?php echo esc_html( $l['pref_intro'] ); ?></p>
            <?php foreach ( $cats as $key => $cat ) : ?>
            <div class="bcm-pref-row">
                <div class="bcm-pref-info">
                    <strong><?php echo esc_html( $cat['label'] ); ?></strong>
                    <span class="bcm-pref-desc">
                        <?php echo esc_html( $l[ 'desc_' . $key ] ?? '' ); ?>
                    </span>
                </div>
                <label class="bcm-pref-toggle">
                    <input type="checkbox" name="bcm_cat" value="<?php echo esc_attr( $key ); ?>"
                        <?php checked( $cat['locked'] ); ?>
                        <?php disabled( $cat['locked'] ); ?>
                        data-locked="<?php echo esc_attr( $cat['locked'] ? '1' : '0' ); ?>">
                    <span class="bcm-pref-slider <?php echo esc_attr( $cat['locked'] ? 'locked' : '' ); ?>"></span>
                </label>
            </div>
            <?php endforeach; ?>
        </div>
        <div class="bcm-pref-footer">
            <?php if ( ! empty( $s['show_tos_checkbox'] ) ) : ?>
            <div class="bcm-tos-row bcm-tos-row--pref">
                <label class="bcm-tos-label">
                    <input type="checkbox" id="bcm-tos-check-pref" class="bcm-tos-check">
                    <span class="bcm-tos-text">
                        <?php echo esc_html( $l['tos_label'] ); ?>
                        <?php if ( ! empty( $s['tos_url'] ) ) : ?>
                            <a href="<?php echo esc_url( $s['tos_url'] ); ?>"
                               target="_blank" rel="noopener noreferrer"
                               class="bcm-tos-link"><?php echo esc_html( $l['tos_link_text'] ); ?></a>
                        <?php else : ?>
                            <?php echo esc_html( $l['tos_link_text'] ); ?>
                        <?php endif; ?>
                        <?php if ( ! empty( $s['privacy_policy_url'] ) ) : ?>
                            <?php echo esc_html( $l['tos_and'] ); ?>
                            <a href="<?php echo esc_url( $s['privacy_policy_url'] ); ?>"
                               target="_blank" rel="noopener noreferrer"
                               class="bcm-tos-link"><?php echo esc_html( $l['privacy_link_text'] ); ?></a>
                        <?php endif; ?>
                    </span>
                </label>
                <span id="bcm-tos-error-pref" class="bcm-tos-error" style="display:none;" role="alert">
                    ⚠ <?php echo esc_html( $l['tos_error'] ); ?>
                </span>
            </div>
            <?php endif; ?>
            <div class="bcm-pref-footer-btns">
                <button id="bcm-pref-reject"  class="bcm-pref-btn bcm-pref-btn-outline"><?php echo esc_html( $s['reject_btn_text'] ); ?></button>
                <button id="bcm-pref-save"    class="bcm-pref-btn bcm-pref-btn-secondary"><?php echo esc_html( $l['pref_save'] ); ?></button>
                <button id="bcm-pref-accept"  class="bcm-pref-btn bcm-pref-btn-primary"><?php echo esc_html( $s['accept_btn_text'] ); ?></button>
            </div>
        </div>
    </div>
</div>

<!-- Re-open widget (GDPR Art. 7.3) -->
<?php if ( ! empty( $s['withdrawal_enabled'] ) ) : ?>
<button id="bcm-reopen" class="bcm-reopen"
        title="<?php echo esc_attr( $l['cookie_settings'] ); ?>"
        style="display:none; --bcm-primary: <?php echo esc_attr( $s['primary_color'] ); ?>;">🍪</button>
<?php endif; ?>
