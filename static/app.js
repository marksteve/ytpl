(function($, undefined) {

  window.YTPL = {models: {}, collections: {}, views: {}};

  _(YTPL.models).extend({
    Video: Backbone.Model.extend({
    })
  });

  _(YTPL.collections).extend({
    Results: Backbone.Collection.extend({
      model: YTPL.models.Video
    }),
    Playlist: Backbone.Collection.extend({
      initialize: function() {
        _.bindAll(this, 'updateVideo');
      },
      model: YTPL.models.Video,
      url: function() {
        return '/pl/' + this.plName;
      },
      comparator: function(model) {
        return model.get('pos');
      },
      updateVideo: function(video) {
        this.get(video.id).set(video);
      }
    })
  });

  YTPL.views.Result = Backbone.View.extend({
    tagName: 'li',
    className: 'cf',
    events: {
      'click': 'addToPL'
    },
    template:
      '<img src="<%= thumbnail.url %>">' +
      '<h3 class="title"><%= title %></h3>' +
      '<span class="author"><%= author %></span>',
    render: function() {
      this.$el.html(_.template(this.template, this.model.toJSON()));
      return this;
    },
    addToPL: function(e) {
      YTPL.playlist.create(this.model.toJSON());
      YTPL.results.reset([]);
    }
  });

  YTPL.views.Search = Backbone.View.extend({
    el: '#search',
    events: {
      'keypress input': 'checkKey'
    },
    initialize: function() {
      this.collection.on('reset', this.showResults, this);
    },
    checkKey: function(e) {
      if (e.keyCode == 13) {
        this.search();
      } else {
        clearTimeout(self.keyTimeout);
        self.keyTimeout = setTimeout(_.bind(this.search, this), 1000);
      }
    },
    search: function(e) {
      var $q = this.$('input');
      var promise = $.ajax({
        url: '/search',
        data: {
          q: $q.val()
        },
        dataType: 'json'
      });

      promise.done(_.bind(function(response) {
        this.collection.reset(response);
      }, this));
    },
    showResults: function(collection) {
      var $results = this.$('#results', this.$el).empty();
      if (collection.length > 0) {
        collection.each(function(model) {
          var view = new YTPL.views.Result({
            model: model
          });
          $results.append(view.render().el);
        }, this);
        $results.show();
      } else {
        this.$('input', this.$el).val('');
        $results.hide();
      }
    }
  });

  YTPL.views.Video = Backbone.View.extend({
    tagName: 'li',
    className: 'cf',
    events: {
      'click .title': 'play',
      'click img': 'play',
      'click .delete': 'delete'
    },
    template:
      '<img src="<%= thumbnail.url %>">' +
      '<a href="#" class="delete">&times;</a>' +
      '<h3 class="title"><%= title %></h3>' +
      '<span class="author"><%= author %></span>',
    render: function() {
      if (this.model.id) {
        this.$el.attr('id', this.model.id);
      }
      this.$el.html(_.template(this.template, this.model.toJSON()));
      if (!YTPL.canEdit) {
        // Remove delete button for non editors
        this.$('.delete').remove();
      }
      return this;
    },
    play: function() {
      YTPL.player.pos = this.model.get('pos');
      YTPL.player.play();
    },
    'delete': function(e) {
      e.preventDefault();
      this.model.destroy({
        success: _.bind(function(model, response) {
          this.remove();
          _(response).each(YTPL.playlist.updateVideo);
        }, this)
      });
    }
  });

  YTPL.views.Playlist = Backbone.View.extend({
    el: '#playlist',
    events: {
      'sortupdate': 'sort'
    },
    initialize: function() {
      this.collection.on('add', this.addVideo, this);
      this.collection.on('reset', this.addVideos, this);
    },
    addVideos: function(collection) {
      if (this.collection.length > 0) {
        this.$el.empty();
      }
      collection.each(this.addVideo, this);
      if (YTPL.canEdit) {
        this.$el.sortable().disableSelection();
      }
    },
    addVideo: function(model) {
      if (this.collection.length == 1) {
        this.$el.empty();
      }
      model.view = new YTPL.views.Video({
        model: model
      });
      this.$el.append(model.view.render().el);
    },
    sort: function(e, ui) {
      var $video = ui.item;
      var id = $video.attr('id');
      var pos = _(this.$el.sortable('toArray')).indexOf(id);
      var video = this.collection.get(id);
      video.save({id: id, pos: pos}, {
        success: _.bind(function(model, response) {
          video.clear(); // save applies changes to the model
          video.set('id', id); // but keep id to be able to update
          _(response).each(YTPL.playlist.updateVideo);
        }, this)
      });
    }
  });

  YTPL.views.Player = Backbone.View.extend({
    pos: 0, // Start with first video
    el: '#player',
    initialize: function() {
      this.collection.on('add', this.playFirstAdd, this);
    },
    setIframe: function() {
      this.ytPlayer = new YT.Player('player', {
        height: '270',
        width: '480',
        events: {
          'onReady': _.bind(this.ready, this),
          'onStateChange': _.bind(this.stateChange, this)
        }
      });
    },
    ready: function(e) {
      // Auto play first video
      this.play();
    },
    play: function() {
      this.collection.sort({silent: true});
      var video = this.collection.at(this.pos);
      if (video) {
        this.ytPlayer.loadVideoById(video.get('vid'));
        this.ytPlayer.playVideo();
        video.view.$el.addClass('playing').siblings().removeClass('playing');
      }
    },
    playFirstAdd: function() {
      if (this.collection.length == 1) {
        this.play();
      }
    },
    stateChange: function(e) {
      // Next video
      if (e.data == YT.PlayerState.ENDED) {
        this.pos++;
        if (this.pos >= this.collection.length) {
          this.pos = 0;
        }
        this.play();
      }
    }
  });

  YTPL.views.Playlists = Backbone.View.extend({
    el: '#playlists',
    events: {
      'change select': 'switchPlaylist',
      'click .share': 'share'
    },
    initialize: function() {
      this.$('select').val(this.options.currPlaylist);
    },
    switchPlaylist: function(e) {
      location.href = '/' + this.$(e.target).val();
    },
    share: function(e) {
      e.preventDefault();
      var $button = $(e.target);
      var promise = $.ajax({url: '/share/' + this.options.currPlaylist});
      $button.html('Sharing&hellip;').prop('disabled', true);
      promise.done(function() {
        $button.html('Shared!');
      });
      promise.fail(function(){
        $button.html('Share failed!');
      });
      promise.always(function() {
        setTimeout(function() {
          $button.html('Share').prop('disabled', false);
        }, 3000);
      });
    }
  });

  YTPL.results = new YTPL.collections.Results();
  YTPL.playlist = new YTPL.collections.Playlist();

  YTPL.Router = Backbone.Router.extend({
    routes: {
      ':plName': 'default'
    },
    'default': function(plName) {
      new YTPL.views.Playlists({currPlaylist: plName});

      YTPL.results.plName = plName;
      YTPL.playlist.plName = plName;

      new YTPL.views.Search({collection: YTPL.results});
      new YTPL.views.Playlist({collection: YTPL.playlist});

      YTPL.playlist.fetch({success: function() {
        YTPL.player = new YTPL.views.Player({collection: YTPL.playlist});
        YTPL.player.setIframe();
      }});
    }
  });

})(jQuery);

function onYouTubePlayerAPIReady() {
  YTPL.router = new YTPL.Router();
  Backbone.history.start({pushState: true});
}